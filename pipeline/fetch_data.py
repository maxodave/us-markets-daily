"""
Scarica l'elenco di S&P 500, Dow Jones e Nasdaq-100 da Wikipedia (con settore GICS/ICB)
e le variazioni di prezzo giornaliere (Yahoo Finance via yfinance), poi salva tutto in
data.json pronto per la dashboard e per il sito.

I tre indici si sovrappongono molto (il Dow e' quasi interamente incluso nell'S&P 500,
e cosi' la maggior parte del Nasdaq-100): per questo NON si tengono tre liste separate.
Si fondono in un unico universo deduplicato per ticker, dove ogni titolo porta un campo
"indices" con l'insieme di indici di cui fa parte (es. ["sp500", "nasdaq100"]). Le
statistiche per singolo indice, piu' avanti nella pipeline, sono un filtro su questo
campo — non un fetch/merge separato.

Il settore usa sempre la taxonomy GICS (S&P 500 e Dow) quando disponibile; solo per i
pochi titoli esclusivamente Nasdaq-100 (non in S&P/Dow) si usa "ICB Industry" come
fallback, perche' la pagina Wikipedia del Nasdaq-100 non pubblica il GICS.

Uso:
    python3 fetch_data.py
"""
import datetime as dt
import json
import re
import sys
import time
import zoneinfo
from io import StringIO

import pandas as pd
import requests
import yfinance as yf

SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
# NON la pagina "Dow Jones Industrial Average" (dal 2026 non ha piu' la tabella dei 30
# titoli, solo la storia dell'indice): la tabella con Symbol/Sector vive nella pagina
# dedicata, esattamente come per S&P 500 e Nasdaq-100 qui sotto. Senza questo la
# finestra Dow Jones esce silenziosamente vuota (fallisce dentro un try/except che
# stampa solo su stderr) — vedi fetch_constituents_dow().
DOW_URL = "https://en.wikipedia.org/wiki/List_of_Dow_Jones_Industrial_Average_companies"
# NON la pagina "Nasdaq-100" (ha solo un elenco senza tabella): la tabella coi ticker
# e i settori vive nella pagina dedicata, con la maiuscola "NASDAQ" nel titolo esatto.
NASDAQ100_URL = "https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies"
FTSEMIB_URL = "https://en.wikipedia.org/wiki/FTSE_MIB"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
CHUNK_SIZE = 80
OUT_FILE = "data.json"
# Elenco snello dei costituenti (simbolo Yahoo + indici) per il job LIVE. Vedi main().
UNIVERSE_FILE = "universe.json"

# Il guardiano della seduta (30 settembre 2026). Vedi guardiano_seduta().
QUOTE_URL = "https://query1.finance.yahoo.com/v7/finance/quote"
QUOTE_FIELDS = "regularMarketPrice,regularMarketPreviousClose,regularMarketTime,exchangeTimezoneName"
QUOTE_BATCH = 50
# Tre fondi che replicano i tre indici: scambiano ogni giorno in cui scambia Wall
# Street, quindi la data della loro ultima chiusura E' l'ultima seduta. Nessun
# calendario delle festivita' da tenere aggiornato a mano.
RIFERIMENTO_SEDUTA = ("SPY", "QQQ", "DIA")


def _flat_columns(df: pd.DataFrame) -> list[str]:
    """Nomi di colonna come stringhe semplici, senza note a pie' di pagina.

    Wikipedia a volte genera header a piu' livelli (pagine con piu' tabelle, come
    quella del Dow) e a volte appende un marcatore di nota al nome della colonna
    (es. "ICB Industry[1]", visto realmente sulla pagina del Nasdaq-100): senza
    questa pulizia un confronto esatto con "ICB Industry" fallisce in silenzio e la
    colonna sembra non esistere.
    """
    cols = []
    for c in df.columns:
        if isinstance(c, tuple):
            c = next((str(x) for x in reversed(c) if str(x) and not str(x).startswith("Unnamed")), str(c[-1]))
        c = re.sub(r"\[.*?\]\s*$", "", str(c)).strip()
        cols.append(c)
    return cols


def clean_name(v) -> str:
    """Il nome di una societa', ripulito dai residui del wikitesto.

    Le tabelle di Wikipedia arrivano con qualche cella sporca: barre verticali
    del markup dei link, riferimenti a note, spazi doppi. Trovato il 4 settembre
    2026 con "ResMed|" — un carattere solo, ma finiva in chiaro sul sito ovunque
    comparisse quel titolo (elenco dei mover, serie, post). Si ripulisce qui,
    all'ingresso, cosi' vale per tutte le viste invece di essere corretto in
    ciascuna.
    """
    t = str(v or "")
    t = re.sub(r"\[.*?\]", "", t)          # note e riferimenti
    t = t.replace("|", " ")                 # residui del markup dei link
    return re.sub(r"\s+", " ", t).strip()


def find_table(tables: list, required_cols: set) -> pd.DataFrame:
    """La pagina del Dow ha piu' tabelle (componenti + storico): si cerca quella giusta
    per nome delle colonne invece di assumere che sia la prima."""
    for df in tables:
        cols = _flat_columns(df)
        if required_cols.issubset(set(cols)):
            out = df.copy()
            out.columns = cols
            return out
    raise ValueError(f"nessuna tabella con le colonne {required_cols} trovata")


def fetch_constituents_sp500() -> pd.DataFrame:
    print("Scarico elenco S&P 500 da Wikipedia...")
    r = requests.get(SP500_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    df = pd.read_html(StringIO(r.text))[0]
    df = df[["Symbol", "Security", "GICS Sector", "GICS Sub-Industry"]].copy()
    df.columns = ["symbol", "name", "sector", "sub_industry"]
    df["yf_symbol"] = df["symbol"].str.replace(".", "-", regex=False)
    print(f"  -> {len(df)} societa' trovate")
    return df


def fetch_constituents_dow() -> pd.DataFrame:
    try:
        print("Scarico elenco Dow Jones da Wikipedia...")
        r = requests.get(DOW_URL, headers=HEADERS, timeout=30)
        r.raise_for_status()
        df = find_table(pd.read_html(StringIO(r.text)), {"Symbol", "Company", "Sector"})
        df = df[["Symbol", "Company", "Sector"]].copy()
        df.columns = ["symbol", "name", "sector"]
        df["sub_industry"] = None
        df["yf_symbol"] = df["symbol"].str.replace(".", "-", regex=False)
        print(f"  -> {len(df)} societa' trovate")
        return df
    except Exception as e:
        print(f"ATTENZIONE: elenco Dow Jones non recuperato ({e}) — "
              f"l'edizione uscira' senza la finestra Dow Jones.", file=sys.stderr)
        return pd.DataFrame(columns=["symbol", "name", "sector", "sub_industry", "yf_symbol"])


def fetch_constituents_nasdaq100() -> pd.DataFrame:
    try:
        print("Scarico elenco Nasdaq-100 da Wikipedia...")
        r = requests.get(NASDAQ100_URL, headers=HEADERS, timeout=30)
        r.raise_for_status()
        df = find_table(pd.read_html(StringIO(r.text)), {"Ticker", "Company"})
        cols = {"Ticker": "symbol", "Company": "name"}
        if "ICB Industry" in df.columns:
            cols["ICB Industry"] = "sector"
        df = df.rename(columns=cols)
        keep = ["symbol", "name"] + (["sector"] if "sector" in df.columns else [])
        df = df[keep].copy()
        if "sector" not in df.columns:
            df["sector"] = None
        df["sub_industry"] = None
        df["yf_symbol"] = df["symbol"].str.replace(".", "-", regex=False)
        print(f"  -> {len(df)} societa' trovate")
        return df
    except Exception as e:
        print(f"ATTENZIONE: elenco Nasdaq-100 non recuperato ({e}) — "
              f"l'edizione uscira' senza la finestra Nasdaq-100.", file=sys.stderr)
        return pd.DataFrame(columns=["symbol", "name", "sector", "sub_industry", "yf_symbol"])


def fetch_constituents_ftsemib() -> pd.DataFrame:
    """FTSE MIB (Borsa Italiana): unico indice qui non americano, tenuto DISGIUNTO
    dagli altri tre invece che unito in "combined" (vedi build_edition.py) — valuta
    e orari di borsa diversi, non ha senso sommarlo agli indici USA.

    Il ticker su Wikipedia e' gia' nella forma che vuole Yahoo Finance (es.
    "ENI.MI"): a differenza di sp500/nasdaq100, qui NON si sostituisce il punto con
    un trattino, altrimenti "ENI.MI" diventerebbe "ENI-MI" e il download fallirebbe.
    Il punto resta anche nel "symbol" mostrato: evita che un ticker italiano si
    scontri per caso con un ticker USA della stessa sigla (es. un ipotetico "ENI"
    americano) quando le liste si fondono per simbolo in merge_constituents().
    """
    try:
        print("Scarico elenco FTSE MIB da Wikipedia...")
        r = requests.get(FTSEMIB_URL, headers=HEADERS, timeout=30)
        r.raise_for_status()
        df = find_table(pd.read_html(StringIO(r.text)), {"Ticker", "Company"})
        cols = {"Ticker": "symbol", "Company": "name"}
        if "ICB Sector" in df.columns:
            cols["ICB Sector"] = "sector"
        df = df.rename(columns=cols)
        keep = ["symbol", "name"] + (["sector"] if "sector" in df.columns else [])
        df = df[keep].copy()
        if "sector" not in df.columns:
            df["sector"] = None
        df["sub_industry"] = None
        df["yf_symbol"] = df["symbol"]
        print(f"  -> {len(df)} societa' trovate")
        return df
    except Exception as e:
        print(f"ATTENZIONE: elenco FTSE MIB non recuperato ({e}) — "
              f"l'edizione uscira' senza la finestra FTSE MIB.", file=sys.stderr)
        return pd.DataFrame(columns=["symbol", "name", "sector", "sub_industry", "yf_symbol"])


def merge_constituents(
    sp500: pd.DataFrame, dow: pd.DataFrame, nasdaq100: pd.DataFrame, ftsemib: pd.DataFrame
) -> pd.DataFrame:
    """Fonde le quattro liste in un unico universo deduplicato per symbol.

    Ogni titolo guadagna "indices": l'elenco di tutti gli indici di cui fa parte.
    L'ordine sp500 -> dow -> nasdaq100 e' anche l'ordine di preferenza per il settore:
    GICS (sp500/dow) vince sempre su ICB (nasdaq100), che si usa solo per completare i
    titoli mai visti nelle prime due liste. FTSE MIB non si sovrappone mai a queste
    tre (ticker italiani, forma "XXX.MI"): entra sempre come voce nuova.
    """
    by_symbol: dict[str, dict] = {}
    for df, idx_name in ((sp500, "sp500"), (dow, "dow"), (nasdaq100, "nasdaq100"), (ftsemib, "ftsemib")):
        for _, row in df.iterrows():
            sym = row["symbol"]
            entry = by_symbol.get(sym)
            if entry is None:
                entry = {
                    "symbol": sym,
                    "name": clean_name(row["name"]),
                    "sector": row.get("sector"),
                    "sub_industry": row.get("sub_industry"),
                    "yf_symbol": row["yf_symbol"],
                    "indices": [],
                }
                by_symbol[sym] = entry
            elif not entry.get("sector") and row.get("sector"):
                entry["sector"] = row["sector"]  # completa con ICB solo se GICS manca
            if idx_name not in entry["indices"]:
                entry["indices"].append(idx_name)

    merged = pd.DataFrame(by_symbol.values())
    print(
        f"Unione indici: {len(merged)} titoli unici "
        f"(S&P 500: {len(sp500)}, Dow Jones: {len(dow)}, Nasdaq-100: {len(nasdaq100)}, "
        f"FTSE MIB: {len(ftsemib)})"
    )
    return merged


def chunked(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def fetch_prices(yf_symbols: list[str]) -> dict:
    """Ritorna {yf_symbol: {'prev_close':.., 'last_close':.., 'pct_change':.., 'date': 'YYYY-MM-DD'}}"""
    results: dict[str, dict] = {}
    chunks = list(chunked(yf_symbols, CHUNK_SIZE))
    for idx, chunk in enumerate(chunks, 1):
        print(f"Scarico prezzi: batch {idx}/{len(chunks)} ({len(chunk)} titoli)...")
        try:
            data = yf.download(
                chunk, period="5d", group_by="ticker", threads=True, progress=False, auto_adjust=False
            )
        except Exception as e:
            print(f"  ! errore batch {idx}: {e}", file=sys.stderr)
            continue

        for sym in chunk:
            try:
                if len(chunk) == 1:
                    closes = data["Close"].dropna()
                else:
                    closes = data[sym]["Close"].dropna()
                if len(closes) < 2:
                    continue
                last_close = float(closes.iloc[-1])
                prev_close = float(closes.iloc[-2])
                pct = (last_close - prev_close) / prev_close * 100
                results[sym] = {
                    "prev_close": round(prev_close, 2),
                    "last_close": round(last_close, 2),
                    "pct_change": round(pct, 2),
                    "date": str(closes.index[-1].date()),
                }
            except Exception:
                continue
        time.sleep(1)
    return results


def moda_delle_date(prices: dict) -> tuple[str | None, dict]:
    """La data condivisa dal maggior numero di titoli (a parita', la piu' recente),
    e il conteggio completo. E' la stessa regola che main() usa per session_date."""
    counts: dict[str, int] = {}
    for p in prices.values():
        counts[p["date"]] = counts.get(p["date"], 0) + 1
    if not counts:
        return None, counts
    return max(counts, key=lambda d: (counts[d], d)), counts


def _conteggio(counts: dict) -> str:
    return " · ".join(f"{d}: {n}" for d, n in sorted(counts.items(), reverse=True))


def fetch_quotes(yf_symbols: list[str]) -> dict:
    """Ultimo prezzo, chiusura precedente e DATA di ciascun titolo, dall'endpoint
    delle quotazioni di Yahoo — non dalla storia giornaliera che usa fetch_prices().

    Ritorna {yf_symbol: {'price':.., 'prev':.., 'date': 'YYYY-MM-DD'}}, dove 'date' e'
    il giorno di regularMarketTime nel fuso della SUA borsa (New York per Wall
    Street, Roma per il FTSE MIB), come le date della storia giornaliera.

    Perche' questo endpoint e non fast_info. fast_info.last_price, che usa il job
    LIVE, e' ricavato dalla stessa storia giornaliera (yfinance: _get_1y_prices):
    avrebbe lo stesso difetto che il guardiano deve coprire. Il LIVE non se ne
    accorge solo perche' non gira mai dopo le 16:25 di New York.

    Una richiesta ogni QUOTE_BATCH simboli; un blocco che fallisce si riprova una
    volta e poi si salta. Mai un'eccezione verso l'alto: se questa fonte non
    risponde, il guardiano non puo' giudicare e lo dice, ma non ferma il giro.
    """
    try:
        from yfinance.data import YfData  # gestisce cookie e "crumb" di Yahoo
        dati = YfData()
    except Exception as e:
        print(f"  ! quotazioni non disponibili ({type(e).__name__}: {e})", file=sys.stderr)
        return {}

    out: dict[str, dict] = {}
    for chunk in chunked(yf_symbols, QUOTE_BATCH):
        for tentativo in (1, 2):
            try:
                r = dati.get(url=QUOTE_URL, params={"symbols": ",".join(chunk), "fields": QUOTE_FIELDS})
                risultati = r.json().get("quoteResponse", {}).get("result", [])
                break
            except Exception as e:
                risultati = []
                if tentativo == 2:
                    print(f"  ! blocco quotazioni saltato ({type(e).__name__}: {e})", file=sys.stderr)
                else:
                    time.sleep(3)
        for q in risultati:
            price, prev, t = q.get("regularMarketPrice"), q.get("regularMarketPreviousClose"), q.get("regularMarketTime")
            if not (price and prev and t):
                continue
            sym = q.get("symbol", "")
            tz = q.get("exchangeTimezoneName") or ("Europe/Rome" if sym.endswith(".MI") else "America/New_York")
            try:
                giorno = dt.datetime.fromtimestamp(int(t), zoneinfo.ZoneInfo(tz)).date()
            except Exception:
                continue
            out[sym] = {"price": float(price), "prev": float(prev), "date": str(giorno)}
        time.sleep(0.5)
    return out


def guardiano_seduta(prices: dict, yf_symbols: list[str]) -> dict:
    """Impedisce all'edizione di raccontare una seduta piu' vecchia dell'ultima.

    IL GUASTO (visto fra il 21 e il 29 settembre 2026, 7 giri su 7). Se il job
    parte dopo le ~20:05 di New York, la storia giornaliera di Yahoo termina UNA
    SEDUTA PRIMA: la barra del giorno appena chiuso non c'e'. La moda delle date la
    prende per buona, e l'edizione racconta la seduta precedente — con numeri veri
    e data vera, solo non l'ultima. Prima di quell'ora il dato e' giusto:

        giri fra le 19:44 e le 20:04 di New York   4 su 4 giusti
        giri fra le 20:14 e le 21:11 di New York   3 su 3 una seduta indietro

    Capita a giorni alterni perche' GitHub consegna lo schedule delle 21:30 UTC
    con 2-4 ore di ritardo, cioe' esattamente a cavallo di quell'ora. E NON
    lasciava traccia: il registro di un giro giusto e quello di uno sbagliato erano
    identici riga per riga. Quando un giro tardivo e' seguito da uno puntuale, una
    seduta si perde per sempre: e' successo a lunedi' 21 settembre.

    COSA FA. Chiede all'endpoint delle quotazioni (fetch_quotes) la data
    dell'ultima chiusura di SPY/QQQ/DIA: quella e' la seduta da raccontare. Poi:
      - se la storia giornaliera arriva a quella seduta, non tocca niente;
      - se e' indietro, prende prezzo e chiusura precedente dalle quotazioni per
        ogni titolo rimasto indietro, e ricalcola la variazione;
      - se anche dopo e' indietro, il giro SI FERMA con un errore. Un'edizione
        che manca si vede, in rosso su GitHub; una seduta sbagliata no — e'
        esattamente il modo in cui questo guasto e' rimasto invisibile per giorni.
    Se le quotazioni non rispondono il guardiano non puo' giudicare: lo scrive, e
    lascia il giro com'era prima che esistesse.

    In ogni caso scrive le date trovate: il prossimo guasto di questo tipo si vede
    nel registro senza dover contare a mano.
    """
    moda, counts = moda_delle_date(prices)
    print(f"Date delle ultime chiusure (storia giornaliera): {_conteggio(counts) or 'nessuna'}")

    quotes = fetch_quotes(list(RIFERIMENTO_SEDUTA) + list(yf_symbols))
    attese = [quotes[s]["date"] for s in RIFERIMENTO_SEDUTA if s in quotes]
    if not attese:
        print("Guardiano: quotazioni di riferimento non disponibili, nessun controllo sulla seduta.")
        return prices
    attesa = max(attese)
    print(f"Seduta di riferimento (quotazioni {'/'.join(RIFERIMENTO_SEDUTA)}): {attesa}")

    if moda is not None and moda >= attesa:
        print(f"Guardiano: seduta {moda}, coincide con il riferimento.")
        return prices

    print(f"Guardiano: la storia giornaliera e' indietro ({moda} contro {attesa}): "
          f"riparo con le quotazioni.")
    # La chiusura precedente si prende dalla STORIA GIORNALIERA quando si puo', non
    # dalle quotazioni. Il giorno dello stacco del dividendo l'endpoint delle
    # quotazioni la rettifica (sottrae il dividendo): misurato il 30 settembre 2026,
    # 12 titoli su 558 — quasi tutti fondi immobiliari a fine trimestre, con la
    # differenza pari al centesimo al dividendo trimestrale. La storia giornaliera
    # (auto_adjust=False) da' invece la chiusura vera, ed e' quella che fetch_prices
    # usa in tutte le altre notti. Quando la storia e' indietro di UNA seduta — il
    # guasto tipico — la sua ultima chiusura E' la chiusura precedente: usarla tiene
    # identico il metodo fra una notte riparata e una no. Solo se la storia manca, o
    # e' indietro di piu' di una seduta, si ripiega sulla chiusura delle quotazioni.
    seduta_prima = moda
    riparati = 0
    for sym in yf_symbols:
        q = quotes.get(sym)
        p = prices.get(sym)
        if not q or q["date"] > attesa:
            continue
        if p is not None and p["date"] >= q["date"]:
            continue
        prev = p["last_close"] if (p is not None and p["date"] == seduta_prima) else q["prev"]
        prices[sym] = {
            "prev_close": round(prev, 2),
            "last_close": round(q["price"], 2),
            "pct_change": round((q["price"] - prev) / prev * 100, 2),
            "date": q["date"],
        }
        riparati += 1

    moda, counts = moda_delle_date(prices)
    print(f"  riparati {riparati} titoli su {len(yf_symbols)} · dopo: {_conteggio(counts)}")
    if moda is None or moda < attesa:
        print(f"\nFERMO: anche dopo la riparazione la seduta e' {moda}, l'ultima e' {attesa}.", file=sys.stderr)
        print("Non scrivo un'edizione che racconterebbe la seduta sbagliata: il sito resta",
              "com'e' e il prossimo giro riprova.", file=sys.stderr)
        sys.exit(1)
    print(f"Guardiano: seduta {moda}, ora coincide con il riferimento.")
    return prices


def bucket_for(pct: float) -> str:
    if pct <= -5:
        return "-10% / -5%"
    if pct <= 0:
        return "-4.9% / 0%"
    if pct <= 2.5:
        return "0.1% / +2.5%"
    if pct <= 10:
        return "+2.6% / +10%"
    if pct <= 20:
        return "+10.1% / +20%"
    return "+20.1% / +inf"


def main():
    sp500 = fetch_constituents_sp500()
    dow = fetch_constituents_dow()
    nasdaq100 = fetch_constituents_nasdaq100()
    ftsemib = fetch_constituents_ftsemib()
    constituents = merge_constituents(sp500, dow, nasdaq100, ftsemib)

    # Un solo fetch prezzi sull'unione: i titoli in piu' indici non vengono scaricati
    # due volte, e i ~545-560 titoli unici restano ben dentro il chunking esistente.
    prices = fetch_prices(constituents["yf_symbol"].tolist())
    # Prima di scegliere la seduta, controlla che la storia giornaliera arrivi
    # davvero all'ultima: dopo le ~20:05 di New York si ferma una seduta prima.
    prices = guardiano_seduta(prices, constituents["yf_symbol"].tolist())

    rows = []
    missing = []
    for _, row in constituents.iterrows():
        p = prices.get(row["yf_symbol"])
        if not p:
            missing.append(row["symbol"])
            continue
        rows.append(
            {
                "symbol": row["symbol"],
                "name": clean_name(row["name"]),
                "sector": row["sector"],
                "sub_industry": row["sub_industry"],
                "indices": row["indices"],
                "date": p["date"],
                "prev_close": p["prev_close"],
                "last_close": p["last_close"],
                "pct_change": p["pct_change"],
                "bucket": bucket_for(p["pct_change"]),
            }
        )

    rows.sort(key=lambda r: r["pct_change"], reverse=True)

    # La data della seduta e' quella CONDIVISA dalla maggioranza dei titoli, non
    # quella del singolo top gainer (rows[0]). Un titolo sospeso o con l'ultima
    # barra mancante su yfinance porta una data vecchia: se capita di essere il
    # mover in cima, "generated_at" (e quindi la "seduta del ..." sul sito)
    # regrediva a quel giorno stantio mentre gli altri 500+ titoli erano freschi.
    # E' successo davvero: il 18 agosto l'edizione mostrava la seduta del 14 perche'
    # il top gainer sul runner GitHub aveva ancora la barra del venerdi'. La moda
    # delle date (a parita', la piu' recente) e' la seduta che l'indice ha davvero
    # scambiato.
    session_date = None
    if rows:
        counts = {}
        for r in rows:
            counts[r["date"]] = counts.get(r["date"], 0) + 1
        session_date = max(counts, key=lambda d: (counts[d], d))

    out = {
        "generated_at": session_date,
        "count": len(rows),
        "missing": missing,
        "companies": rows,
    }
    with open(OUT_FILE, "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    # universe.json: l'elenco SNELLO (simbolo Yahoo + indici) di tutto l'universo,
    # committato nel repo. Serve al job LIVE (fetch_live_quotes.py, ogni 15 min):
    # data.json e' gitignorato e comunque il job live non gira fetch_data, quindi
    # senza questo file non saprebbe QUALI titoli quotare per i top/worst del
    # momento. Cambia di rado (i costituenti sono stabili), quindi committarlo non
    # sporca la cronologia. Vedi fetch_live_quotes.py.
    universe = [
        {
            "yf_symbol": r["yf_symbol"],
            "symbol": r["symbol"],
            "name": clean_name(r["name"]),
            "indices": r["indices"],
        }
        for _, r in constituents.iterrows()
    ]
    with open(UNIVERSE_FILE, "w") as f:
        json.dump({"generated_at": session_date, "companies": universe}, f, indent=2, ensure_ascii=False)
    print(f"Universo LIVE salvato in {UNIVERSE_FILE} ({len(universe)} simboli).")

    print(f"\nCompletato: {len(rows)} societa' salvate in {OUT_FILE}")
    if missing:
        print(f"  {len(missing)} simboli senza dati (delisted/sospesi/rinominati): {', '.join(missing[:20])}"
              + (" ..." if len(missing) > 20 else ""))


if __name__ == "__main__":
    main()
