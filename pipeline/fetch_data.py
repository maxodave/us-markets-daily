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
import json
import re
import sys
import time
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
                    "name": row["name"],
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
                "name": row["name"],
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

    out = {
        "generated_at": rows[0]["date"] if rows else None,
        "count": len(rows),
        "missing": missing,
        "companies": rows,
    }
    with open(OUT_FILE, "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print(f"\nCompletato: {len(rows)} societa' salvate in {OUT_FILE}")
    if missing:
        print(f"  {len(missing)} simboli senza dati (delisted/sospesi/rinominati): {', '.join(missing[:20])}"
              + (" ..." if len(missing) > 20 else ""))


if __name__ == "__main__":
    main()
