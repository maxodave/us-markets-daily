"""Scrive live.json: livello e variazione % dei quattro indici seguiti, per la
striscia "LIVE" del sito. Il browser non puo' leggere Yahoo direttamente (CORS
bloccato), quindi i dati li raccoglie qui un workflow GitHub e la pagina legge il
file (stessa origine).

Volutamente LEGGERO: quattro simboli, nessuna notizia, nessun calcolo pesante —
cosi' puo' girare spesso (ogni poche ore) senza costare come la pipeline piena.

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


def quote(symbol: str) -> dict | None:
    """Ultimo prezzo e chiusura precedente. None se Yahoo non risponde per questo
    simbolo: un indice mancante non deve far fallire tutta la striscia."""
    try:
        t = yf.Ticker(symbol)
        fi = getattr(t, "fast_info", None) or {}
        last = fi.get("last_price") or fi.get("lastPrice")
        prev = fi.get("previous_close") or fi.get("previousClose")
        if last is None or prev is None:
            # Ripiego: due giorni di chiusure dal grafico.
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


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    indices = []
    for idx in INDICES:
        q = quote(idx["symbol"])
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
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "live.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Scritto {path} ({len(indices)}/4 indici, mercato {'aperto' if market_open else 'chiuso'}).")


if __name__ == "__main__":
    main()
