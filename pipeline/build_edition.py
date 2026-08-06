"""
Crea l'edizione del giorno in editions/YYYY-MM-DD.json.

Convenzione date (come una vera newsletter di mercato):
  - la data dell'EDIZIONE e' il giorno di pubblicazione (oggi);
  - il contenuto riguarda l'ULTIMA SEDUTA chiusa (in genere ieri), cioe'
    data.json -> generated_at.
Esempio: l'edizione del 5 agosto racconta la seduta del 4 agosto.

Il resoconto in italiano viene generato in modo DETERMINISTICO dai dati
(nessuna IA), cosi' il job automatico di 00:01 produce sempre una pagina
completa da solo. Se esiste un commento scritto a mano (o con Claude) per la
stessa seduta in market_summary_it.json, viene usato come paragrafo di apertura
in aggiunta al resoconto automatico.

Le edizioni non vengono mai sovrascritte a meno di --force: l'archivio e' la
cronologia del sito.

Uso:
    python3 build_edition.py            # crea l'edizione di oggi se manca
    python3 build_edition.py --force    # rigenera l'edizione di oggi
"""
import json
import os
import re
import sys
from datetime import datetime

from mover_reason import pick_reason

DATA_FILE = "data.json"
FEED_FILE = "feed_news.json"
MANUAL_SUMMARY_FILE = "market_summary_it.json"
EDITIONS_DIR = "editions"

MESI_IT = {
    1: "gennaio", 2: "febbraio", 3: "marzo", 4: "aprile", 5: "maggio", 6: "giugno",
    7: "luglio", 8: "agosto", 9: "settembre", 10: "ottobre", 11: "novembre", 12: "dicembre",
}

# Notizie da mostrare nel feed visuale dell'edizione
FEED_CATEGORIES = ("mercati", "italia", "crypto", "tech", "scienza")
MAX_FEED_ITEMS = 40
TOP_MOVERS = 8
# Quanti mover citare nel paragrafo che riassume le notizie della seduta. Pochi e
# spiegati vale piu' di otto elencati: la lista completa e' comunque nelle due
# colonne accanto al testo.
NARRATED_MOVERS = 3


def italian_date(date_str: str) -> str:
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return f"{d.day} {MESI_IT[d.month]} {d.year}"
    except Exception:
        return date_str or "n/d"


def fmt_pct(v: float) -> str:
    return f"{'+' if v > 0 else ''}{v:.2f}%".replace(".", ",")


def build_auto_report(companies: list[dict], session_date: str) -> dict:
    """Resoconto deterministico della seduta, in italiano. Nessuna IA coinvolta."""
    ups = [c for c in companies if c["pct_change"] > 0]
    downs = [c for c in companies if c["pct_change"] < 0]
    flat = [c for c in companies if c["pct_change"] == 0]
    ordered = sorted(companies, key=lambda c: c["pct_change"], reverse=True)
    gainers = [movers_entry(c) for c in ordered[:TOP_MOVERS]]
    losers = [movers_entry(c) for c in reversed(ordered[-TOP_MOVERS:])]

    avg = sum(c["pct_change"] for c in companies) / len(companies) if companies else 0.0

    # settori migliori/peggiori per variazione media
    by_sector: dict[str, list[float]] = {}
    for c in companies:
        by_sector.setdefault(c["sector"], []).append(c["pct_change"])
    sector_avg = sorted(
        ((s, sum(v) / len(v)) for s, v in by_sector.items()), key=lambda x: x[1], reverse=True
    )
    best_sectors = sector_avg[:3]
    worst_sectors = list(reversed(sector_avg[-3:]))

    paragraphs = [
        (
            f"Nella seduta del {italian_date(session_date)} l'S&P 500 ha chiuso con "
            f"{len(ups)} societa' in rialzo, {len(downs)} in ribasso"
            + (f" e {len(flat)} invariate" if flat else "")
            + f", su {len(companies)} titoli monitorati. La variazione media dell'indice "
            f"e' stata di {fmt_pct(avg)}."
        ),
        (
            "Settori con la variazione media migliore: "
            + "; ".join(f"{s} ({fmt_pct(v)})" for s, v in best_sectors)
            + ". Settori piu' debolli: "
            + "; ".join(f"{s} ({fmt_pct(v)})" for s, v in worst_sectors)
            + "."
        ),
    ]
    movers_para = build_movers_paragraph(gainers, losers)
    if movers_para:
        paragraphs.append(movers_para)

    return {
        "stats": {
            "n_up": len(ups),
            "n_down": len(downs),
            "n_flat": len(flat),
            "n_total": len(companies),
            "avg_pct": round(avg, 2),
            "best_sectors": [{"sector": s, "avg_pct": round(v, 2)} for s, v in best_sectors],
            "worst_sectors": [{"sector": s, "avg_pct": round(v, 2)} for s, v in worst_sectors],
        },
        "paragraphs": paragraphs,
        "gainers": gainers,
        "losers": losers,
    }


def narrate_mover(m: dict) -> str:
    """Un mover in una frase: nome, ticker, variazione e, se c'e', la notizia che
    la spiega con la testata. Senza notizia si ferma alla percentuale: meglio dire
    solo il fatto che riempire con una motivazione che non risulta."""
    base = f"{m['name']} ({m['symbol']}, {fmt_pct(m['pct_change'])})"
    r = m.get("reason")
    if not r:
        return base
    return f"{base}, dove {r['source']} riporta: «{r['title']}»"


def build_movers_paragraph(gainers: list[dict], losers: list[dict]) -> str:
    up = "; ".join(narrate_mover(m) for m in gainers[:NARRATED_MOVERS])
    down = "; ".join(narrate_mover(m) for m in losers[:NARRATED_MOVERS])
    parts = []
    if up:
        parts.append(f"In cima alla seduta: {up}.")
    if down:
        parts.append(f"In fondo: {down}.")
    return " ".join(parts)


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
        "reason": pick_reason(c, news_key="news_recent"),
        "news": _slim((c.get("news_recent") or [])[:6]),
        "news_historical": _slim((c.get("news_historical") or [])[:3]),
    }


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


def headline_for(session_date: str, auto: dict, manual: dict | None) -> str:
    if manual and manual.get("headline"):
        return manual["headline"]
    s = auto["stats"]
    if s["n_up"] > s["n_down"] * 1.5:
        tone = "Seduta ampiamente positiva a Wall Street"
    elif s["n_down"] > s["n_up"] * 1.5:
        tone = "Seduta in prevalenza negativa a Wall Street"
    else:
        tone = "Seduta mista a Wall Street"
    top = auto["gainers"][0] if auto["gainers"] else None
    if top:
        return f"{tone}: {top['name']} {fmt_pct(top['pct_change'])} guida i rialzi"
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

    auto = build_auto_report(companies, session_date)
    manual = load_manual_summary(session_date)

    edition = {
        "edition_date": edition_date,
        "edition_date_it": italian_date(edition_date),
        "session_date": session_date,
        "session_date_it": italian_date(session_date),
        "headline": headline_for(session_date, auto, manual),
        "auto_report": auto,
        "manual_commentary_html": (manual or {}).get("summary_html"),
        "manual_highlights": (manual or {}).get("highlights", []),
        "feed": load_feed_items(),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    with open(out_path, "w") as f:
        json.dump(edition, f, indent=2, ensure_ascii=False)

    print(
        f"Edizione creata: {out_path}\n"
        f"  titolo edizione: {edition['edition_date_it']} (seduta del {edition['session_date_it']})\n"
        f"  {len(edition['feed'])} notizie nel feed, "
        f"commento manuale: {'presente' if manual else 'assente (solo resoconto automatico)'}"
    )


if __name__ == "__main__":
    main()
