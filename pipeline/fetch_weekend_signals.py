"""
Raccoglie i pochi mercati che si muovono DAVVERO mentre Wall Street e' chiusa, e
li misura dalla chiusura di venerdi'. Scrive weekend_signals.json.

Perche' esiste: le edizioni di domenica e lunedi' non hanno una seduta nuova da
raccontare (vedi weekend_edition.py). Ripetere i gainer/loser di venerdi' per tre
giorni e' esattamente il difetto da togliere. Ma "nessuna seduta" non vuol dire
"nessun dato": crypto, futures sugli indici, oro, petrolio e valute scambiano nel
fine settimana, e la loro variazione dalla chiusura di venerdi' e' l'unica cifra
onestamente NUOVA che si possa mettere in un'edizione del weekend.

Cosa NON e': una previsione. Il file dice solo "questi strumenti, che restano
aperti, si sono mossi cosi' da quando ha chiuso Wall Street". L'interpretazione
resta al lettore, come per tutto il resto del progetto.

Cosa e' disponibile quando:
  - crypto: sempre, 24/7. E' il dato che c'e' sicuramente sia domenica sia lunedi';
  - futures su indici (ES/NQ/YM), oro, petrolio: riaprono la domenica alle 18:00
    ET (mezzanotte in Italia). L'edizione di domenica quindi NON li trova (chiusi
    da venerdi' sera), quella di lunedi' li trova appena riaperti;
  - valute: riaprono anche loro la domenica sera.
Gli strumenti senza scambi nella finestra vengono semplicemente OMESSI: meglio un
pannello con tre righe vere che uno con dieci righe di cui sette ferme a venerdi'.

Mai fatale: se yfinance non risponde, il file non viene scritto (o resta quello di
ieri, che build_edition scarta perche' vecchio) e l'edizione esce senza il
pannello. Vedi build_edition.py.

Uso:
    python3 fetch_weekend_signals.py                # riferimento: data.json
    python3 fetch_weekend_signals.py 2026-08-14     # riferimento esplicito (debug)
"""
import json
import sys
from datetime import datetime, time, timedelta, timezone

import yfinance as yf

DATA_FILE = "data.json"
OUT_FILE = "weekend_signals.json"

# Ora di chiusura di Wall Street in UTC (16:00 ET). Tutto cio' che e' scambiato
# DOPO questo istante del venerdi' e' movimento di fine settimana, ed e' quello
# che il pannello misura. Le tre ore che passano prima della chiusura dei futures
# (17:00 ET) restano dentro la finestra: sono minuti di venerdi', ma attribuirli
# al weekend e' un errore di pochi centesimi, mentre spostare il taglio a 17:00
# escluderebbe la chiusura della borsa, che e' il riferimento che il lettore ha
# in mente ("da quando ha chiuso Wall Street").
US_CLOSE_UTC = time(20, 0)

# (simbolo yfinance, nome EN, nome IT, gruppo). L'ordine e' quello di lettura.
INSTRUMENTS = [
    ("BTC-USD", "Bitcoin", "Bitcoin", "crypto"),
    ("ETH-USD", "Ethereum", "Ethereum", "crypto"),
    ("SOL-USD", "Solana", "Solana", "crypto"),
    ("XRP-USD", "XRP", "XRP", "crypto"),
    ("ES=F", "S&P 500 futures", "Futures S&P 500", "futures"),
    ("NQ=F", "Nasdaq-100 futures", "Futures Nasdaq-100", "futures"),
    ("YM=F", "Dow Jones futures", "Futures Dow Jones", "futures"),
    ("GC=F", "Gold", "Oro", "commodities"),
    ("CL=F", "WTI crude oil", "Petrolio WTI", "commodities"),
    ("EURUSD=X", "Euro / US dollar", "Euro / dollaro", "fx"),
    ("DX-Y.NYB", "US dollar index", "Indice del dollaro", "fx"),
]

GROUP_LABELS = {
    "crypto": {"en": "Crypto (trades 24/7)", "it": "Crypto (aperto 24/7)"},
    "futures": {"en": "Index futures", "it": "Futures sugli indici"},
    "commodities": {"en": "Commodities", "it": "Materie prime"},
    "fx": {"en": "Currencies", "it": "Valute"},
}
GROUP_ORDER = ("crypto", "futures", "commodities", "fx")

# Sotto questa soglia il movimento non e' un segnale, e' rumore di quotazione: lo
# strumento resta nel pannello (dire "fermo" e' informazione) ma non viene mai
# citato nel testo come movimento degno di nota.
NOTEWORTHY_PCT = 1.0


def reference_cutoff(session_date: str) -> datetime:
    """Istante di chiusura della seduta di riferimento, in UTC."""
    d = datetime.strptime(session_date, "%Y-%m-%d").date()
    return datetime.combine(d, US_CLOSE_UTC, tzinfo=timezone.utc)


def series_for(symbol: str):
    """Barre orarie degli ultimi giorni, indicizzate in UTC.

    Orarie e non giornaliere: i futures riaprono la domenica alle 18:00 ET, e con
    le barre giornaliere quella riapertura o non esiste ancora o viene etichettata
    come il giorno dopo — l'edizione di lunedi' notte li perderebbe tutti. Con le
    barre orarie basta guardare l'ultima. Se l'orario non e' disponibile si ricade
    sul giornaliero, che per le crypto e' comunque sufficiente.
    """
    t = yf.Ticker(symbol)
    for kwargs in ({"period": "8d", "interval": "60m"}, {"period": "12d", "interval": "1d"}):
        try:
            h = t.history(**kwargs, auto_adjust=False)
        except Exception:
            continue
        if h is None or h.empty or "Close" not in h:
            continue
        h = h.dropna(subset=["Close"])
        if h.empty:
            continue
        idx = h.index
        # Le barre giornaliere possono arrivare senza fuso: si assume UTC, che per
        # un confronto con una soglia delle 20:00 e' l'ipotesi conservativa.
        h = h.tz_localize("UTC") if idx.tz is None else h.tz_convert("UTC")
        return h
    return None


def measure(symbol: str, cutoff: datetime) -> dict | None:
    """Ultimo prezzo e variazione dalla chiusura di venerdi'.

    Restituisce None quando lo strumento non ha scambiato dopo la chiusura: e'
    il caso normale dei futures nell'edizione di domenica, e non e' un errore.
    """
    h = series_for(symbol)
    if h is None:
        return None
    before = h[h.index <= cutoff]
    after = h[h.index > cutoff]
    if before.empty or after.empty:
        return None
    ref = float(before["Close"].iloc[-1])
    last = float(after["Close"].iloc[-1])
    if not ref:
        return None
    last_at = after.index[-1]
    return {
        "last": round(last, 4 if last < 10 else 2),
        "pct_change": round((last / ref - 1) * 100, 2),
        "reference_close": round(ref, 4 if ref < 10 else 2),
        "as_of_utc": last_at.strftime("%Y-%m-%d %H:%M UTC"),
    }


def collect(session_date: str) -> list[dict]:
    cutoff = reference_cutoff(session_date)
    print(f"Riferimento: chiusura del {session_date} ({cutoff:%Y-%m-%d %H:%M} UTC)")
    rows = []
    for symbol, name_en, name_it, group in INSTRUMENTS:
        try:
            m = measure(symbol, cutoff)
        except Exception as e:
            print(f"  ! {symbol}: {type(e).__name__}: {e}")
            continue
        if not m:
            print(f"  - {symbol}: nessuno scambio dopo la chiusura, omesso")
            continue
        rows.append({"symbol": symbol, "name_en": name_en, "name_it": name_it, "group": group, **m})
        print(f"  + {symbol}: {m['pct_change']:+.2f}% (ultimo {m['as_of_utc']})")
    return rows


def group_rows(rows: list[dict]) -> list[dict]:
    out = []
    for key in GROUP_ORDER:
        items = [r for r in rows if r["group"] == key]
        if items:
            out.append({"key": key, "label": GROUP_LABELS[key], "instruments": items})
    return out


def write(session_date: str, rows: list[dict], path: str = OUT_FILE) -> None:
    out = {
        "reference_session": session_date,
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "noteworthy_pct": NOTEWORTHY_PCT,
        "groups": group_rows(rows),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)


# Oltre questa eta' il file va rifatto anche se e' della seduta giusta: domenica e
# lunedi' notte condividono la stessa seduta di riferimento (venerdi'), quindi
# senza questo controllo l'edizione di lunedi' ripubblicherebbe le quotazioni di
# domenica — cioe' esattamente il difetto che questa funzionalita' elimina.
MAX_AGE_HOURS = 6


def is_fresh(session_date: str, path: str = OUT_FILE) -> bool:
    try:
        with open(path, encoding="utf-8") as f:
            sig = json.load(f)
    except (FileNotFoundError, ValueError):
        return False
    if sig.get("reference_session") != session_date:
        return False
    try:
        fetched = datetime.strptime(sig["fetched_at"], "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc)
    except (KeyError, ValueError):
        return False
    return datetime.now(timezone.utc) - fetched < timedelta(hours=MAX_AGE_HOURS)


def ensure(session_date: str, path: str = OUT_FILE) -> bool:
    """Aggiorna weekend_signals.json se serve. Non solleva mai.

    La chiama build_edition.py quando l'edizione e' un recap, cosi' il pannello
    dei segnali non ha bisogno di un passo in piu' nel workflow di GitHub — che
    andrebbe modificato dall'editor web, per via degli scope OAuth (vedi README).
    """
    if is_fresh(session_date, path):
        print(f"Segnali del fine settimana gia' aggiornati ({path}).")
        return True
    try:
        rows = collect(session_date)
    except Exception as e:
        print(f"ATTENZIONE: segnali del fine settimana non recuperati ({type(e).__name__}: {e}).", file=sys.stderr)
        return False
    if not rows:
        return False
    try:
        write(session_date, rows, path)
    except Exception as e:
        print(f"ATTENZIONE: segnali del fine settimana non scritti ({type(e).__name__}: {e}).", file=sys.stderr)
        return False
    return True


def main():
    date_arg = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else None
    if date_arg:
        session_date = date_arg
    else:
        try:
            with open(DATA_FILE) as f:
                session_date = json.load(f).get("generated_at")
        except FileNotFoundError:
            session_date = None
    if not session_date:
        print("ERRORE: nessuna seduta di riferimento (manca data.json).", file=sys.stderr)
        sys.exit(1)

    rows = collect(session_date)
    if not rows:
        print("Nessuno strumento con scambi dopo la chiusura: file non scritto.", file=sys.stderr)
        return

    write(session_date, rows)
    print(f"\nCompletato: {len(rows)} strumenti in {OUT_FILE}")


if __name__ == "__main__":
    main()
