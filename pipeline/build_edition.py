"""
Crea l'edizione del giorno in editions/YYYY-MM-DD.json.

Convenzione date (come una vera newsletter di mercato):
  - la data dell'EDIZIONE e' il giorno di pubblicazione (oggi);
  - il contenuto riguarda l'ULTIMA SEDUTA chiusa (in genere ieri), cioe'
    data.json -> generated_at.
Esempio: l'edizione del 5 agosto racconta la seduta del 4 agosto.

Il resoconto e' generato in modo DETERMINISTICO dai dati (nessuna IA), sia in
inglese sia in italiano: i NUMERI si calcolano una volta sola
(build_stats_and_movers), il TESTO si scrive due volte con gli stessi valori
(build_paragraphs, con lang="en"/"it"). Non e' una traduzione — e' lo stesso
calcolo raccontato in due lingue — perche' un errore di traduzione su un dato
di fatto (una percentuale, un conteggio) non e' un rischio accettabile su un
sito che pubblica di notte senza revisione.

Multi-indice: ogni titolo in data.json porta un campo "indices" (fetch_data.py)
con gli indici di cui fa parte (sp500/dow/nasdaq100). Il resoconto si calcola
per ciascun indice (filtro su "indices") PIU' una vista "combined" — che e'
semplicemente lo stesso calcolo senza filtro, sull'intero universo deduplicato:
nessuna logica di fusione in piu', perche' l'universo e' gia' deduplicato alla
fonte (fetch_data.py).

Compatibilita': il campo "auto_report" di livello radice resta quello di sempre
(solo S&P 500, solo italiano) — build_publish.py e build_dashboard.py continuano
a leggerlo senza modifiche. La nuova struttura multi-indice/bilingue vive in un
campo AGGIUNTIVO, "auto_report_by_index".

Se esiste un commento scritto a mano (o da generate_commentary.py) per la stessa
seduta in market_summary.json, viene usato come paragrafo di apertura in aggiunta
al resoconto automatico.

Le edizioni non vengono mai sovrascritte a meno di --force: l'archivio e' la
cronologia del sito.

Uso:
    python3 build_edition.py            # crea l'edizione di oggi se manca
    python3 build_edition.py --force    # rigenera l'edizione di oggi
"""
import json
import os
import sys
from datetime import datetime

from mover_reason import pick_reason

DATA_FILE = "data.json"
FEED_FILE = "feed_news.json"
MANUAL_SUMMARY_FILE = "market_summary.json"
EDITIONS_DIR = "editions"

MESI_IT = {
    1: "gennaio", 2: "febbraio", 3: "marzo", 4: "aprile", 5: "maggio", 6: "giugno",
    7: "luglio", 8: "agosto", 9: "settembre", 10: "ottobre", 11: "novembre", 12: "dicembre",
}
MONTHS_EN = {
    1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June",
    7: "July", 8: "August", 9: "September", 10: "October", 11: "November", 12: "December",
}

INDEX_KEYS = ("sp500", "dow", "nasdaq100", "combined")
INDEX_LABELS = {
    "sp500": {"it": "l'S&P 500", "en": "the S&P 500"},
    "dow": {"it": "il Dow Jones", "en": "the Dow Jones"},
    "nasdaq100": {"it": "il Nasdaq-100", "en": "the Nasdaq-100"},
    "combined": {"it": "l'insieme dei tre indici", "en": "the combined three indices"},
}

# Notizie da mostrare nel feed visuale dell'edizione
FEED_CATEGORIES = ("mercati", "italia", "crypto", "tech", "scienza")
MAX_FEED_ITEMS = 40
TOP_MOVERS = 8
# Quanti mover citare nel paragrafo che riassume le notizie della seduta. Pochi e
# spiegati vale piu' di otto elencati: la lista completa e' comunque nelle due
# colonne accanto al testo.
NARRATED_MOVERS = 3
# Società minime perché un settore entri nella classifica migliori/peggiori.
# Vedi build_auto_report(): serve a non far vincere un settore da una società sola.
MIN_SECTOR_SAMPLE = 3


def italian_date(date_str: str) -> str:
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return f"{d.day} {MESI_IT[d.month]} {d.year}"
    except Exception:
        return date_str or "n/d"


def english_date(date_str: str) -> str:
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return f"{MONTHS_EN[d.month]} {d.day}, {d.year}"
    except Exception:
        return date_str or "n/a"


def fmt_pct(v: float, lang: str = "it") -> str:
    s = f"{'+' if v > 0 else ''}{v:.2f}%"
    return s.replace(".", ",") if lang == "it" else s


def _slim(items: list[dict]) -> list[dict]:
    return [{"title": n["title"], "source": n["source"], "link": n["link"]} for n in items]


def movers_entry(c: dict) -> dict:
    # Recenti e storiche restano SEPARATE: per spiegare la seduta di ieri vale solo
    # una notizia recente. Mescolarle porta ad attribuzioni contraddittorie (un
    # titolo salito del 10% "spiegato" da una notizia di giorni prima che parlava
    # di un calo). Lo storico serve al contesto, non come causa.
    return {
        "symbol": c["symbol"],
        "name": c["name"],
        "sector": c["sector"],
        "pct_change": c["pct_change"],
        "last_close": c["last_close"],
        "indices": c.get("indices") or [],
        "reason": pick_reason(c, news_key="news_recent"),
        "news": _slim((c.get("news_recent") or [])[:6]),
        "news_historical": _slim((c.get("news_historical") or [])[:3]),
    }


def build_stats_and_movers(companies: list[dict]) -> tuple[dict, list[dict], list[dict]]:
    """Calcola stats/gainers/losers UNA VOLTA: nessuna lingua qui, solo numeri."""
    ups = [c for c in companies if c["pct_change"] > 0]
    downs = [c for c in companies if c["pct_change"] < 0]
    flat = [c for c in companies if c["pct_change"] == 0]
    ordered = sorted(companies, key=lambda c: c["pct_change"], reverse=True)
    gainers = [movers_entry(c) for c in ordered[:TOP_MOVERS]]
    losers = [movers_entry(c) for c in reversed(ordered[-TOP_MOVERS:])]

    avg = sum(c["pct_change"] for c in companies) / len(companies) if companies else 0.0

    by_sector: dict[str, list[float]] = {}
    for c in companies:
        by_sector.setdefault(c.get("sector") or "N/D", []).append(c["pct_change"])
    # Un settore con una o due societa' non ha una "variazione media" che significhi
    # qualcosa: nella vista combinata i titoli esclusivamente Nasdaq-100 portano
    # nomi di settore ICB che l'S&P 500 non usa, e ne e' bastato uno (SPCX,
    # "Telecommunications", n=1) per apparire come settore piu' forte della seduta
    # a +6,14%. Sotto la soglia il settore resta nei dati, ma fuori dalla classifica.
    ranked = sorted(
        (
            (s, sum(v) / len(v))
            for s, v in by_sector.items()
            if len(v) >= MIN_SECTOR_SAMPLE
        ),
        key=lambda x: x[1],
        reverse=True,
    )
    best_sectors = ranked[:3]
    worst_sectors = list(reversed(ranked[-3:]))

    stats = {
        "n_up": len(ups),
        "n_down": len(downs),
        "n_flat": len(flat),
        "n_total": len(companies),
        "avg_pct": round(avg, 2),
        "best_sectors": [{"sector": s, "avg_pct": round(v, 2)} for s, v in best_sectors],
        "worst_sectors": [{"sector": s, "avg_pct": round(v, 2)} for s, v in worst_sectors],
    }
    return stats, gainers, losers


def narrate_mover(m: dict, lang: str) -> str:
    """Un mover in una frase: nome, ticker, variazione e, se c'e', la notizia che
    la spiega con la testata. Senza notizia si ferma alla percentuale: meglio dire
    solo il fatto che riempire con una motivazione che non risulta."""
    base = f"{m['name']} ({m['symbol']}, {fmt_pct(m['pct_change'], lang)})"
    r = m.get("reason")
    if not r:
        return base
    if lang == "it":
        return f"{base}, dove {r['source']} riporta: «{r['title']}»"
    return f"{base}, where {r['source']} reports: “{r['title']}”"


def build_movers_paragraph(gainers: list[dict], losers: list[dict], lang: str) -> str:
    up = "; ".join(narrate_mover(m, lang) for m in gainers[:NARRATED_MOVERS])
    down = "; ".join(narrate_mover(m, lang) for m in losers[:NARRATED_MOVERS])
    parts = []
    if lang == "it":
        if up:
            parts.append(f"In cima alla seduta: {up}.")
        if down:
            parts.append(f"In fondo: {down}.")
    else:
        if up:
            parts.append(f"Leading the session: {up}.")
        if down:
            parts.append(f"At the bottom: {down}.")
    return " ".join(parts)


def build_paragraphs(
    index_key: str, stats: dict, gainers: list[dict], losers: list[dict], session_date: str, lang: str
) -> list[str]:
    """Resoconto in prosa per UN indice e UNA lingua, dai numeri gia' calcolati.

    Per index_key="sp500", lang="it" questo produce ESATTAMENTE il testo che il
    codice generava prima dell'introduzione multi-indice (verificato con un
    confronto byte a byte): e' il campo "auto_report" di livello radice.
    """
    label = INDEX_LABELS[index_key][lang]
    ups, downs, flat, total = stats["n_up"], stats["n_down"], stats["n_flat"], stats["n_total"]
    avg = fmt_pct(stats["avg_pct"], lang)

    if lang == "it":
        p1 = (
            f"Nella seduta del {italian_date(session_date)} {label} ha chiuso con "
            f"{ups} societa' in rialzo, {downs} in ribasso"
            + (f" e {flat} invariate" if flat else "")
            + f", su {total} titoli monitorati. La variazione media dell'indice "
            f"e' stata di {avg}."
        )
        best = "; ".join(f"{s['sector']} ({fmt_pct(s['avg_pct'], 'it')})" for s in stats["best_sectors"])
        worst = "; ".join(f"{s['sector']} ({fmt_pct(s['avg_pct'], 'it')})" for s in stats["worst_sectors"])
        p2 = f"Settori con la variazione media migliore: {best}. Settori piu' debolli: {worst}."
    else:
        p1 = (
            f"In the {english_date(session_date)} session {label} closed with "
            f"{ups} stocks higher, {downs} lower"
            + (f" and {flat} unchanged" if flat else "")
            + f", out of {total} tracked. The average move was {avg}."
        )
        best = "; ".join(f"{s['sector']} ({fmt_pct(s['avg_pct'], 'en')})" for s in stats["best_sectors"])
        worst = "; ".join(f"{s['sector']} ({fmt_pct(s['avg_pct'], 'en')})" for s in stats["worst_sectors"])
        p2 = f"Best-performing sectors by average move: {best}. Weakest: {worst}."

    paragraphs = [p1, p2]
    movers_para = build_movers_paragraph(gainers, losers, lang)
    if movers_para:
        paragraphs.append(movers_para)
    return paragraphs


def load_feed_items() -> list[dict]:
    try:
        with open(FEED_FILE) as f:
            feed = json.load(f)
    except FileNotFoundError:
        return []
    items = [i for i in feed.get("items", []) if i.get("category") in FEED_CATEGORIES]
    # prima quelli con immagine, mantenendo l'ordine cronologico dentro i due gruppi
    with_img = [i for i in items if i.get("image")]
    without = [i for i in items if not i.get("image")]
    return (with_img + without)[:MAX_FEED_ITEMS]


def load_manual_summary(session_date: str) -> dict | None:
    try:
        with open(MANUAL_SUMMARY_FILE) as f:
            ms = json.load(f)
    except FileNotFoundError:
        return None
    if ms.get("date") != session_date:
        return None  # commento scritto per un'altra seduta: non riusarlo
    return ms


def headline_for(session_date: str, stats: dict, gainers: list[dict], lang: str, manual_headline: str | None) -> str:
    if manual_headline:
        return manual_headline
    if lang == "it":
        if stats["n_up"] > stats["n_down"] * 1.5:
            tone = "Seduta ampiamente positiva a Wall Street"
        elif stats["n_down"] > stats["n_up"] * 1.5:
            tone = "Seduta in prevalenza negativa a Wall Street"
        else:
            tone = "Seduta mista a Wall Street"
        top = gainers[0] if gainers else None
        if top:
            return f"{tone}: {top['name']} {fmt_pct(top['pct_change'], 'it')} guida i rialzi"
        return tone
    else:
        if stats["n_up"] > stats["n_down"] * 1.5:
            tone = "Broadly positive session on Wall Street"
        elif stats["n_down"] > stats["n_up"] * 1.5:
            tone = "Broadly negative session on Wall Street"
        else:
            tone = "Mixed session on Wall Street"
        top = gainers[0] if gainers else None
        if top:
            return f"{tone}: {top['name']} {fmt_pct(top['pct_change'], 'en')} leads gainers"
        return tone


def main():
    force = "--force" in sys.argv

    with open(DATA_FILE) as f:
        data = json.load(f)
    companies = data["companies"]
    session_date = data.get("generated_at")
    edition_date = datetime.now().strftime("%Y-%m-%d")

    os.makedirs(EDITIONS_DIR, exist_ok=True)
    out_path = os.path.join(EDITIONS_DIR, f"{edition_date}.json")
    if os.path.exists(out_path) and not force:
        print(f"Edizione {edition_date} gia' presente: {out_path} (usa --force per rigenerarla)")
        return

    manual = load_manual_summary(session_date)

    auto_report_by_index = {}
    for index_key in INDEX_KEYS:
        if index_key == "combined":
            subset = companies
        else:
            subset = [c for c in companies if index_key in (c.get("indices") or ["sp500"])]
        stats, gainers, losers = build_stats_and_movers(subset)
        auto_report_by_index[index_key] = {
            "stats": stats,
            "gainers": gainers,
            "losers": losers,
            "paragraphs": {
                "en": build_paragraphs(index_key, stats, gainers, losers, session_date, "en"),
                "it": build_paragraphs(index_key, stats, gainers, losers, session_date, "it"),
            },
        }

    # Campo di livello radice "auto_report": stesso identico contenuto di sempre
    # (solo S&P 500, solo italiano) — punta agli stessi oggetti di
    # auto_report_by_index["sp500"], cosi' le due viste non possono mai divergere.
    sp500_block = auto_report_by_index["sp500"]
    legacy_auto_report = {
        "stats": sp500_block["stats"],
        "paragraphs": sp500_block["paragraphs"]["it"],
        "gainers": sp500_block["gainers"],
        "losers": sp500_block["losers"],
    }

    manual_headline_it = (manual or {}).get("headline")
    manual_headline_en = (manual or {}).get("headline_en")
    headline_it = headline_for(session_date, sp500_block["stats"], sp500_block["gainers"], "it", manual_headline_it)
    headline_en = headline_for(session_date, sp500_block["stats"], sp500_block["gainers"], "en", manual_headline_en)

    edition = {
        "edition_date": edition_date,
        "edition_date_it": italian_date(edition_date),
        "edition_date_en": english_date(edition_date),
        "session_date": session_date,
        "session_date_it": italian_date(session_date),
        "session_date_en": english_date(session_date),
        "headline": headline_it,
        "headline_en": headline_en,
        "auto_report": legacy_auto_report,
        "auto_report_by_index": auto_report_by_index,
        "manual_commentary_html": (manual or {}).get("summary_html_it") or (manual or {}).get("summary_html"),
        "manual_commentary_html_en": (manual or {}).get("summary_html_en"),
        "manual_highlights": (manual or {}).get("highlights", []),
        "feed": load_feed_items(),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    with open(out_path, "w") as f:
        json.dump(edition, f, indent=2, ensure_ascii=False)

    print(
        f"Edizione creata: {out_path}\n"
        f"  titolo edizione: {edition['edition_date_it']} (seduta del {edition['session_date_it']})\n"
        f"  indici: " + ", ".join(f"{k} ({auto_report_by_index[k]['stats']['n_total']} titoli)" for k in INDEX_KEYS) + "\n"
        f"  {len(edition['feed'])} notizie nel feed, "
        f"commento manuale: {'presente' if manual else 'assente (solo resoconto automatico)'}"
    )


if __name__ == "__main__":
    main()
