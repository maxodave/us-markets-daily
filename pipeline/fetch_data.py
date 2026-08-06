"""
Scarica l'elenco S&P 500 (Wikipedia, con settore/sotto-settore GICS) e le variazioni
di prezzo giornaliere (Yahoo Finance via yfinance), poi salva tutto in data.json
pronto per la dashboard.

Uso:
    python3 fetch_data.py
"""
import json
import sys
import time
from io import StringIO

import pandas as pd
import requests
import yfinance as yf

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
CHUNK_SIZE = 80
OUT_FILE = "data.json"


def fetch_constituents() -> pd.DataFrame:
    print("Scarico elenco S&P 500 da Wikipedia...")
    r = requests.get(WIKI_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    df = pd.read_html(StringIO(r.text))[0]
    df = df[["Symbol", "Security", "GICS Sector", "GICS Sub-Industry"]].copy()
    df.columns = ["symbol", "name", "sector", "sub_industry"]
    df["yf_symbol"] = df["symbol"].str.replace(".", "-", regex=False)
    print(f"  -> {len(df)} societa' trovate")
    return df


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
    constituents = fetch_constituents()
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
