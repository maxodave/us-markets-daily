"""
Recupera titoli di notizie pubbliche (via Google News RSS) per TUTTE le societa'
dell'S&P 500 e le allega a data.json. Le ricerche sono filtrate per dare priorita'
alle fonti indicate dall'utente (Reuters, Bloomberg, FT, WSJ, CNBC, MarketWatch,
Barron's, NYT, Forbes, Yahoo Finance, CertificateJournal, FinanzaOnline,
WallStreetItalia, ANSA); se un titolo e' poco coperto da queste fonti, la ricerca
si allarga automaticamente a tutte le fonti indicizzate da Google News.

Le notizie sono divise in:
  - news_recent: notizie degli ultimi RECENT_DAYS giorni (query "when:")
  - news_historical: notizie precedenti, da HISTORICAL_DAYS a RECENT_DAYS giorni fa
    (query esplicita "after:/before:", cosi' anche per i titoli con volume di notizie
    altissimo nei giorni recenti compaiono comunque le notizie di settimane prima —
    utile per capire se qualcosa aveva gia' anticipato il movimento)

Calcola anche un conteggio grezzo di tono lessicale (parole "positive"/"negative"
ricorrenti nei titoli) — e' materiale descrittivo da leggere, NON un punteggio di
investimento ne' un consiglio su cosa comprare.

Uso:
    python3 fetch_news.py                 # tutte le 503 societa' (~15-20 min)
    python3 fetch_news.py --movers-only    # solo i titoli agli estremi (~1-2 min)

--movers-only serve al job su GitHub Actions, che deve produrre solo l'edizione
pubblica: interrogare 503 societa' da un runner sarebbero ~1000 richieste a Google
News da un IP di datacenter, con rischio concreto di rate-limit. Le societa' non
interrogate restano con liste di notizie vuote, quindi la forma di data.json non
cambia. La dashboard privata continua a usare il default.
"""
import json
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import feedparser

DATA_FILE = "data.json"
HISTORICAL_DAYS = 30
RECENT_DAYS = 3
MAX_RECENT = 6
MAX_HISTORICAL = 6
MAX_WORKERS = 8
MIN_RESULTS_BEFORE_FALLBACK = 3
# Quante societa' per lato interrogare con --movers-only (vedi select_movers)
MOVERS_ONLY_N = 12

# Fonti finanziarie preferite dall'utente per le notizie sui singoli titoli
# (il sottoinsieme della lista completa che tipicamente copre notizie societarie).
PRIORITY_SITES = [
    "reuters.com", "bloomberg.com", "ft.com", "wsj.com", "cnbc.com",
    "marketwatch.com", "barrons.com", "nytimes.com", "forbes.com",
    "finance.yahoo.com", "certificatejournal.it", "finanzaonline.com",
    "wallstreetitalia.com", "ansa.it",
]
SITE_FILTER = "(" + " OR ".join(f"site:{s}" for s in PRIORITY_SITES) + ")"

POSITIVE_WORDS = {
    "surge", "surges", "surging", "soar", "soars", "soaring", "jump", "jumps", "jumping",
    "rally", "rallies", "rallying", "beat", "beats", "record", "upgrade", "upgraded",
    "gain", "gains", "gaining", "boom", "booming", "blowout", "outperform", "outperforms",
    "strong", "boost", "boosts", "rise", "rises", "rising", "climb", "climbs", "bullish",
    "win", "wins", "winning", "top", "tops", "exceed", "exceeds", "raise", "raises",
}
NEGATIVE_WORDS = {
    "plunge", "plunges", "plunging", "slump", "slumps", "slumping", "miss", "misses",
    "missed", "downgrade", "downgraded", "cut", "cuts", "cutting", "lawsuit", "probe",
    "investigation", "decline", "declines", "declining", "warn", "warns", "warning",
    "crash", "crashes", "sink", "sinks", "sinking", "tumble", "tumbles", "tumbling",
    "fall", "falls", "falling", "drop", "drops", "dropping", "bearish", "loss", "losses",
    "recall", "layoff", "layoffs", "fraud", "weak", "weakens", "underperform",
}


def _parse_entries(d) -> list[dict]:
    out = []
    for e in d.entries:
        try:
            dt = parsedate_to_datetime(e.get("published", ""))
        except Exception:
            dt = None
        out.append(
            {
                "title": e.get("title", ""),
                "source": e.get("source", {}).get("title", ""),
                "published": e.get("published", ""),
                "published_dt": dt,
                "link": e.get("link", ""),
            }
        )
    out.sort(key=lambda x: x["published_dt"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return out


def _search(q: str) -> list[dict]:
    url = f"https://news.google.com/rss/search?q={urllib.parse.quote(q)}&hl=en-US&gl=US&ceid=US:en"
    return _parse_entries(feedparser.parse(url))


def fetch_recent(query: str) -> list[dict]:
    prioritized = _search(f"{query} stock {SITE_FILTER} when:{RECENT_DAYS}d")
    if len(prioritized) >= MIN_RESULTS_BEFORE_FALLBACK:
        return prioritized
    # fallback: titolo poco coperto dalle fonti prioritarie, allarga a tutte le fonti
    return _search(f"{query} stock when:{RECENT_DAYS}d")


def fetch_historical(query: str, reference_date: datetime) -> list[dict]:
    """Notizie della finestra precedente (da HISTORICAL_DAYS a RECENT_DAYS giorni fa).

    NB: qui NON si applica SITE_FILTER. Google News ignora gli operatori
    after:/before: quando sono combinati con la lunga catena di site:, e
    restituisce comunque i risultati piu' recenti — rendendo lo storico un
    duplicato delle notizie recenti. Per lo storico conta la copertura di cosa
    e' uscito prima, non la testata, quindi si interroga senza filtro fonti.
    Il rispetto della finestra temporale e' comunque garantito a valle da
    split_recent_historical(), che filtra sulle date effettive.
    """
    after = (reference_date - timedelta(days=HISTORICAL_DAYS)).strftime("%Y-%m-%d")
    before = (reference_date - timedelta(days=RECENT_DAYS)).strftime("%Y-%m-%d")
    return _search(f"{query} stock after:{after} before:{before}")


def tone_count(headlines: list[dict]) -> dict:
    pos = neg = 0
    for h in headlines:
        words = set(w.strip(".,:;!?()'\"").lower() for w in h["title"].split())
        if words & POSITIVE_WORDS:
            pos += 1
        if words & NEGATIVE_WORDS:
            neg += 1
    return {"positive": pos, "negative": neg}


def strip_dt(headlines: list[dict]) -> list[dict]:
    return [{k: v for k, v in h.items() if k != "published_dt"} for h in headlines]


def split_by_date(
    recent_raw: list[dict], historical_raw: list[dict], reference_date: datetime
) -> tuple[list[dict], list[dict]]:
    """Divide le notizie sulle DATE effettive, non fidandosi degli operatori Google.

    Google News a volte ignora after:/before: e restituisce comunque i risultati
    piu' recenti: senza questo controllo lo "storico" diventa un duplicato delle
    notizie recenti. Qui una notizia entra nello storico solo se la sua data cade
    davvero nella finestra precedente e non e' gia' tra le recenti.
    """
    recent_cutoff = reference_date - timedelta(days=RECENT_DAYS)
    historical_cutoff = reference_date - timedelta(days=HISTORICAL_DAYS)

    recent, recent_links = [], set()
    for h in recent_raw:
        dt = h["published_dt"]
        if dt is not None and dt < recent_cutoff:
            continue
        if h["link"] in recent_links:
            continue
        recent_links.add(h["link"])
        recent.append(h)
        if len(recent) >= MAX_RECENT:
            break

    historical, seen = [], set(recent_links)
    for h in historical_raw:
        dt = h["published_dt"]
        if dt is None or not (historical_cutoff <= dt < recent_cutoff):
            continue  # senza data affidabile non si puo' garantire la finestra
        if h["link"] in seen:
            continue
        seen.add(h["link"])
        historical.append(h)
        if len(historical) >= MAX_HISTORICAL:
            break

    return recent, historical


def fetch_for_company(c: dict, reference_date: datetime) -> dict:
    query = f"{c['name']} ({c['symbol']})"
    try:
        recent_raw = fetch_recent(query)
    except Exception:
        recent_raw = []
    try:
        historical_raw = fetch_historical(query, reference_date)
    except Exception:
        historical_raw = []

    recent, historical = split_by_date(recent_raw, historical_raw, reference_date)
    tone = tone_count(recent + historical)
    return {
        "symbol": c["symbol"],
        "news_recent": strip_dt(recent),
        "news_historical": strip_dt(historical),
        "tone": tone,
    }


def select_movers(companies: list[dict]) -> list[dict]:
    """I titoli agli estremi della seduta, i soli che finiscono nell'edizione.

    MOVERS_ONLY_N e' piu' alto degli 8 mover che build_edition.py pubblica: se un
    titolo non ha notizie utilizzabili, quelli subito dietro sono comunque coperti.

    Il taglio e' PER INDICE (S&P 500, Dow Jones, Nasdaq-100), non globale: un
    movimento estremo per il Dow (30 titoli, oscillazioni tipicamente piu' contenute)
    quasi mai finirebbe nel taglio globale, e le sue notizie non verrebbero mai
    recuperate. Ogni titolo compare in "indices" (vedi fetch_data.py); i tre insiemi
    si uniscono deduplicando per symbol, cosi' un titolo in piu' indici (es. Apple) si
    interroga una sola volta.
    """
    selected: dict[str, dict] = {}
    for index_name in ("sp500", "dow", "nasdaq100"):
        in_index = [c for c in companies if index_name in (c.get("indices") or [])]
        ordered = sorted(in_index, key=lambda c: c["pct_change"], reverse=True)
        for c in ordered[:MOVERS_ONLY_N] + ordered[-MOVERS_ONLY_N:]:
            selected[c["symbol"]] = c
    return list(selected.values())


def main():
    movers_only = "--movers-only" in sys.argv

    with open(DATA_FILE) as f:
        data = json.load(f)

    companies = data["companies"]
    ref_date_str = data.get("generated_at")
    reference_date = (
        datetime.strptime(ref_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if ref_date_str
        else datetime.now(timezone.utc)
    )

    targets = select_movers(companies) if movers_only else companies
    scope = "i soli mover della seduta" if movers_only else "tutte le societa'"
    print(
        f"Recupero notizie (recenti <= {RECENT_DAYS}g, storiche {RECENT_DAYS}-{HISTORICAL_DAYS}g) "
        f"per {len(targets)} societa' ({scope})..."
    )

    results_by_symbol = {}
    done = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(fetch_for_company, c, reference_date): c["symbol"] for c in targets}
        for fut in as_completed(futures):
            r = fut.result()
            results_by_symbol[r["symbol"]] = r
            done += 1
            if done % 25 == 0 or done == len(targets):
                print(f"  ... {done}/{len(targets)} completati")

    for c in companies:
        r = results_by_symbol.get(c["symbol"], {})
        c["news_recent"] = r.get("news_recent", [])
        c["news_historical"] = r.get("news_historical", [])
        c["tone"] = r.get("tone", {"positive": 0, "negative": 0})
        c.pop("news", None)  # retro-compat: rimuove il vecchio campo unico da run precedenti

    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    n_with_news = sum(1 for c in companies if c["news_recent"] or c["news_historical"])
    print(f"\nCompletato: {n_with_news}/{len(companies)} societa' con almeno una notizia, salvate in {DATA_FILE}")


if __name__ == "__main__":
    main()
