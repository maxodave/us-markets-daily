"""Scrive live.json: livello e variazione % dei quattro indici seguiti PIU' i
top 10 / worst 10 titoli del momento, per la vista "LIVE" del sito. Il browser
non puo' leggere Yahoo direttamente (CORS bloccato), quindi i dati li raccoglie
qui un workflow GitHub e la pagina legge il file (stessa origine).

I MOVER del momento (non della sola chiusura) sono cio' che rende viva la
dashboard: lo striscione in basso e la lista nella scheda LIVE cambiano a ogni
run (ogni 15 min durante la seduta). Si calcolano su TUTTO il mercato USA
(NYSE + Nasdaq + NYSE American) filtrato per liquidita', letto da
universe_live.json (lo scrive build_live_universe.py ogni notte). Prima si
guardavano solo i tre indici, e una societa' fuori da quelli non poteva comparire
nemmeno crollando: il 18 agosto 2026 Klarna faceva -22% e non si vedeva. Il FTSE
MIB resta fuori perche' Milano e' gia' chiusa mentre Wall Street contratta.
Durante la seduta l'ultima barra giornaliera di yfinance E' il prezzo corrente,
quindi "ultima vs penultima chiusura" da' la variazione intraday.

Se manca l'universo o Yahoo non risponde per abbastanza titoli, i mover si
OMETTONO (niente chiave "movers"): la pagina ricade sui mover della seduta
dell'edizione. Meglio nessun dato che dati sbagliati.

Uso:  python3 fetch_live_quotes.py [cartella_output]
      (default: cartella corrente -> live.json)
"""
import json
import os
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import yfinance as yf

# Fuso della borsa: lo stato "aperto/chiuso" si calcola QUI, non in UTC. La
# versione precedente confrontava l'ora UTC con 13:30-20:00 cablate, cioe' la
# finestra dell'ora legale: da novembre a marzo (New York UTC-5) la borsa apriva
# alle 14:30 UTC e il file diceva "chiusa" per la prima ora di seduta, poi
# "aperta" per un'ora dopo la campana. Con il fuso vero il cambio d'ora si
# gestisce da se', come fa gia' il browser nella pagina.
NY_TZ = ZoneInfo("America/New_York")
MARKET_OPEN_MIN = 9 * 60 + 30    # 09:30 ET
MARKET_CLOSE_MIN = 16 * 60       # 16:00 ET

# Simboli Yahoo dei quattro indici mostrati nella striscia LIVE.
INDICES = [
    {"key": "sp500", "label": "S&P 500", "symbol": "^GSPC"},
    {"key": "nasdaq100", "label": "Nasdaq-100", "symbol": "^NDX"},
    {"key": "dow", "label": "Dow Jones", "symbol": "^DJI"},
    {"key": "ftsemib", "label": "FTSE MIB", "symbol": "FTSEMIB.MI"},
]

# Universo dei mover LIVE, in ordine di preferenza:
#  1) universe_live.json — TUTTO il mercato USA (NYSE + Nasdaq + NYSE American)
#     filtrato per liquidita', scritto ogni notte da build_live_universe.py. E' la
#     lista giusta: una societa' fuori dai tre indici (Klarna, NYSE) puo' comparire.
#  2) universe.json — i soli costituenti dei tre indici (503+30+102). Ripiego, usato
#     se il file sopra manca: meglio 518 titoli che nessun mover.
LIVE_UNIVERSE_FILE = "universe_live.json"
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
    """I titoli su cui calcolare i mover del momento, normalizzati a
    {yf_symbol, symbol, name}. Prima l'universo USA liquido, poi i tre indici."""
    for path in (os.path.join(base_dir, LIVE_UNIVERSE_FILE), LIVE_UNIVERSE_FILE):
        try:
            with open(path, encoding="utf-8") as f:
                companies = json.load(f).get("companies", [])
            if companies:
                print(f"  universo LIVE: {len(companies)} societa' liquide da {os.path.basename(path)}.")
                # Nel listino ufficiale il ticker e' gia' quello di Yahoo (solo simboli
                # semplici, vedi build_live_universe.py): symbol == yf_symbol.
                return [
                    {"yf_symbol": c["symbol"], "symbol": c["symbol"], "name": c.get("name", "")}
                    for c in companies
                ]
        except (FileNotFoundError, ValueError):
            continue

    for path in (os.path.join(base_dir, UNIVERSE_FILE), UNIVERSE_FILE):
        try:
            with open(path, encoding="utf-8") as f:
                companies = json.load(f).get("companies", [])
            us = [c for c in companies if set(c.get("indices") or []) & set(US_INDEX_KEYS)]
            if us:
                print(f"  universo LIVE: ripiego sui {len(us)} titoli dei tre indici "
                      f"({os.path.basename(path)}).")
                return [
                    {"yf_symbol": c["yf_symbol"], "symbol": c["symbol"], "name": c.get("name", "")}
                    for c in us
                ]
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


def us_market_open(now_utc: datetime) -> bool:
    """Borsa USA aperta adesso? Calcolato in ora di New York, quindi giusto anche
    d'inverno. Euristica solo per l'etichetta: i giorni di festa non sono nel
    calendario, e lo stato che la pagina mostra lo ricalcola comunque il browser."""
    ny = now_utc.astimezone(NY_TZ)
    if ny.weekday() >= 5:
        return False
    mins = ny.hour * 60 + ny.minute
    return MARKET_OPEN_MIN <= mins < MARKET_CLOSE_MIN


def payload_unchanged(path: str, data: dict) -> bool:
    """I dati sono identici a quelli gia' su disco, a parte l'orario di scrittura?

    Serve a non riscrivere il file per niente. Il campo "updated" cambia a ogni
    run per definizione, quindi il workflow vedeva SEMPRE una modifica e
    committava a ogni giro: a mercati chiusi voleva dire decine di commit con gli
    stessi numeri, e altrettante ripubblicazioni di GitHub Pages (che ha un tetto
    indicativo di 10 build all'ora, condiviso con il job dell'edizione).
    Confrontando tutto TRANNE "updated" il controllo diventa vero.
    """
    try:
        with open(path, encoding="utf-8") as f:
            old = json.load(f)
    except (FileNotFoundError, ValueError):
        return False
    strip = lambda d: {k: v for k, v in d.items() if k != "updated"}
    return strip(old) == strip(data)


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    indices = []
    for idx in INDICES:
        q = quote_index(idx["symbol"])
        if q:
            indices.append({"key": idx["key"], "label": idx["label"], "pct": q["pct"], "last": q["last"]})
            print(f"  {idx['label']}: {q['pct']:+.2f}%")

    # Borsa USA aperta? Calcolato in ora di New York (vedi us_market_open):
    # euristica per l'etichetta della striscia, non per i dati.
    now = datetime.now(timezone.utc)
    market_open = us_market_open(now)

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

    # A mercati CHIUSI, se i numeri sono gli stessi, il file non si tocca: cosi'
    # il workflow non trova nulla da committare e GitHub Pages non ripubblica per
    # niente. A mercati APERTI si riscrive sempre, anche a numeri identici: li'
    # l'orario di "updated" e' un'informazione (la pagina lo usa per dire da
    # quanto i dati sono fermi, e per non etichettare "ora" una lista vecchia).
    if not market_open and payload_unchanged(path, data):
        print(f"Dati identici a mercati chiusi: {path} lasciato invariato "
              f"(nessun commit, nessuna ripubblicazione).")
        return

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Scritto {path} ({len(indices)}/4 indici, mercato {'aperto' if market_open else 'chiuso'}"
          f"{', con mover' if movers else ', senza mover'}).")


if __name__ == "__main__":
    main()
