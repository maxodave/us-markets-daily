"""Scrive live.json: livello e variazione % dei quattro indici seguiti PIU' i
top 10 / worst 10 titoli del momento, per la vista "LIVE" del sito. Il browser
non puo' leggere Yahoo direttamente (CORS bloccato), quindi i dati li raccoglie
qui un workflow GitHub e la pagina legge il file (stessa origine).

I MOVER del momento (non della sola chiusura) sono cio' che rende viva la
dashboard: lo striscione in basso e la lista nella scheda LIVE cambiano a ogni
run (ogni 15 min durante la seduta). Si calcolano sull'universo USA
(sp500/dow/nasdaq100) letto da universe.json — il FTSE MIB resta fuori perche'
Milano e' gia' chiusa mentre Wall Street contratta, quindi mostrerebbe numeri
fermi. Durante la seduta l'ultima barra giornaliera di yfinance E' il prezzo
corrente, quindi "ultima vs penultima chiusura" da' la variazione intraday.

Se universe.json manca o Yahoo non risponde per abbastanza titoli, i mover si
OMETTONO (niente chiave "movers"): la pagina ricade sui mover della seduta
dell'edizione. Meglio nessun dato che dati sbagliati.

Uso:  python3 fetch_live_quotes.py [cartella_output]
      (default: cartella corrente -> live.json)
"""
import json
import os
import sys
from datetime import datetime, timezone

import yfinance as yf

# Simboli Yahoo dei quattro indici mostrati nella striscia LIVE.
INDICES = [
    {"key": "sp500", "label": "S&P 500", "symbol": "^GSPC"},
    {"key": "nasdaq100", "label": "Nasdaq-100", "symbol": "^NDX"},
    {"key": "dow", "label": "Dow Jones", "symbol": "^DJI"},
    {"key": "ftsemib", "label": "FTSE MIB", "symbol": "FTSEMIB.MI"},
]

UNIVERSE_FILE = "universe.json"
# Solo Wall Street per i mover del momento: il FTSE MIB (borsa di Milano) chiude
# nel primo pomeriggio USA, quindi durante la seduta americana darebbe variazioni
# ferme. Vedi il docstring.
US_INDEX_KEYS = ("sp500", "dow", "nasdaq100")
TOP_N = 10           # quanti gainer e quanti loser tenere
CHUNK_SIZE = 80      # come fetch_data.py: batch di download per non superare i limiti
# Sotto questa copertura si sospetta un fetch troncato/limitato (Yahoo throttla gli
# IP dei runner): meglio non pubblicare mover che potrebbero essere sbagliati.
MIN_COVERAGE = 0.5


def quote_index(symbol: str) -> dict | None:
    """Ultimo prezzo e chiusura precedente di un indice. None se Yahoo non risponde:
    un indice mancante non deve far fallire tutta la striscia."""
    try:
        t = yf.Ticker(symbol)
        fi = getattr(t, "fast_info", None) or {}
        last = fi.get("last_price") or fi.get("lastPrice")
        prev = fi.get("previous_close") or fi.get("previousClose")
        if last is None or prev is None:
            hist = t.history(period="2d")
            if len(hist) >= 2:
                last = float(hist["Close"].iloc[-1])
                prev = float(hist["Close"].iloc[-2])
            elif len(hist) == 1:
                last = prev = float(hist["Close"].iloc[-1])
        if not last or not prev:
            return None
        return {"last": round(float(last), 2), "pct": round((float(last) / float(prev) - 1) * 100, 2)}
    except Exception as e:
        print(f"  ! {symbol}: {type(e).__name__}: {e}", file=sys.stderr)
        return None


def load_universe(base_dir: str) -> list[dict]:
    """L'universo USA da universe.json (scritto da fetch_data.py). Vuoto se manca."""
    for path in (os.path.join(base_dir, UNIVERSE_FILE), UNIVERSE_FILE):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            companies = data.get("companies", [])
            return [c for c in companies if set(c.get("indices") or []) & set(US_INDEX_KEYS)]
        except (FileNotFoundError, ValueError):
            continue
    return []


def chunked(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def compute_movers(universe: list[dict]) -> dict | None:
    """Top 10 / worst 10 per variazione intraday. None se la copertura del fetch e'
    troppo bassa (probabile throttling): in quel caso la pagina usa i mover della
    seduta dell'edizione invece di numeri inaffidabili."""
    if not universe:
        return None
    by_symbol = {c["yf_symbol"]: c for c in universe}
    symbols = list(by_symbol)
    rows = []
    for chunk in chunked(symbols, CHUNK_SIZE):
        try:
            data = yf.download(
                chunk, period="2d", group_by="ticker", threads=True, progress=False, auto_adjust=False
            )
        except Exception as e:
            print(f"  ! batch mover: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        for sym in chunk:
            try:
                closes = (data["Close"] if len(chunk) == 1 else data[sym]["Close"]).dropna()
                if len(closes) < 2:
                    continue
                last, prev = float(closes.iloc[-1]), float(closes.iloc[-2])
                if not prev:
                    continue
                c = by_symbol[sym]
                rows.append({"symbol": c["symbol"], "name": c["name"], "pct": round((last / prev - 1) * 100, 2)})
            except Exception:
                continue

    coverage = len(rows) / max(1, len(symbols))
    print(f"  mover: {len(rows)}/{len(symbols)} titoli quotati (copertura {coverage:.0%}).")
    if coverage < MIN_COVERAGE:
        print("  ! copertura troppo bassa: ometto i mover (la pagina usa quelli della seduta).", file=sys.stderr)
        return None

    rows.sort(key=lambda r: r["pct"], reverse=True)
    gainers = rows[:TOP_N]
    losers = list(reversed(rows[-TOP_N:])) if len(rows) >= TOP_N else list(reversed(rows))
    return {"gainers": gainers, "losers": losers, "universe": len(rows)}


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    indices = []
    for idx in INDICES:
        q = quote_index(idx["symbol"])
        if q:
            indices.append({"key": idx["key"], "label": idx["label"], "pct": q["pct"], "last": q["last"]})
            print(f"  {idx['label']}: {q['pct']:+.2f}%")

    # Borsa USA aperta? 13:30–20:00 UTC nei giorni feriali (9:30–16:00 ET, ora
    # legale). Euristica solo per l'etichetta della striscia, non per i dati.
    now = datetime.now(timezone.utc)
    weekday = now.weekday() < 5
    market_open = weekday and (now.hour * 60 + now.minute) >= 13 * 60 + 30 and now.hour < 20

    data = {
        "updated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "market_open": bool(market_open),
        "indices": indices,
    }

    movers = compute_movers(load_universe(out_dir))
    if movers:
        data["movers"] = movers
        print(f"  mover pubblicati: {len(movers['gainers'])} su, {len(movers['losers'])} giu'.")

    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "live.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Scritto {path} ({len(indices)}/4 indici, mercato {'aperto' if market_open else 'chiuso'}"
          f"{', con mover' if movers else ', senza mover'}).")


if __name__ == "__main__":
    main()
