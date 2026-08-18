"""Costruisce universe_live.json: l'elenco dei titoli USA LIQUIDI su cui calcolare i
top 10 / peggiori 10 del momento nella vista LIVE.

PERCHE' ESISTE. La vista LIVE prima guardava solo i costituenti dei tre indici
(S&P 500 + Dow + Nasdaq-100, 518 titoli): una societa' quotata a Wall Street ma
fuori da quegli indici non poteva comparire nemmeno crollando del 22%. E'
successo davvero il 18 agosto 2026 con Klarna (KLAR, -22%, NYSE, fuori da tutti e
tre gli indici). Qui l'universo diventa TUTTO il mercato USA: NYSE, Nasdaq e NYSE
American, dal listino ufficiale di Nasdaq Trader.

PERCHE' FILTRATO. In una classifica per variazione PERCENTUALE vincono quasi
sempre i titoli col prezzo piu' basso e meno scambiati: un titolo da 0,08 $ che
muove 0,6 milioni di dollari fa -31% e scavalca Klarna che ne muove 416. Misurato
sui dati del 18 agosto 2026: senza filtro Klarna era l'11a peggiore (FUORI dalla
top 10), scavalcata da titoli illiquidi; col filtro diventa la 1a. Il filtro NON
esclude le societa' piccole per dimensione — Klarna capitalizza ~5,7 miliardi ed
entra prima. Esclude i casi in cui il prezzo si muove senza scambi veri.

PERCHE' UN PASSO A SE'. Quotare 5.500 titoli richiede ~5 minuti: troppo per un job
che gira ogni 15 minuti, e un carico che Yahoo prima o poi limiterebbe. Quindi la
selezione si fa UNA VOLTA AL GIORNO qui (nel job notturno) e il job LIVE quota
solo le ~850 sopravvissute, in circa un minuto.

Uso:  python3 build_live_universe.py [cartella_output]
"""
import json
import os
import re
import sys
import time

import requests
import yfinance as yf

SYMBOL_DIR_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqtraded.txt"
OUT_FILE = "universe_live.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

# Soglie di liquidita'. Vedi il docstring per la misura che le giustifica.
MIN_DOLLAR_VOL = 50_000_000   # scambi del giorno, in dollari
MIN_PRICE = 5.0               # esclude i penny stock, dove l'1% e' un centesimo

CHUNK_SIZE = 200
# Sotto questa copertura il listino non e' stato quotato abbastanza: si tiene il
# file del giorno prima invece di pubblicare un universo dimezzato.
MIN_COVERAGE = 0.6

EXCHANGES = {"Q": "Nasdaq", "N": "NYSE", "A": "NYSE American", "P": "NYSE Arca", "Z": "BATS"}
# Righe che non sono azioni di una societa': warrant, unit, diritti, privilegiate.
NOISE = re.compile(r"(Warrant|Unit|Right|Preferred|Depositary|% Note|Subordinated|When Issued)", re.I)
# Suffissi del listino ufficiale, inutili da mostrare ("Klarna Group plc Ordinary Shares").
SUFFIX = re.compile(
    r"\s*[-–]?\s*(Ordinary Shares|Common Stock|Common Shares|Class [A-Z] Common Stock"
    r"|Class [A-Z] Ordinary Shares|American Depositary Shares|Shares of Beneficial Interest"
    r"|Ordinary Share|Common Stock, \$?[\d.]+ par value)\b.*$", re.I)


def clean_name(raw: str) -> str:
    name = SUFFIX.sub("", raw).strip(" ,-–")
    return (name or raw)[:44]


def load_listings() -> list[dict]:
    """Tutte le azioni USA dal listino ufficiale. Lista vuota se non raggiungibile."""
    try:
        r = requests.get(SYMBOL_DIR_URL, headers=HEADERS, timeout=40)
        r.raise_for_status()
    except Exception as e:
        print(f"ATTENZIONE: listino non raggiungibile ({type(e).__name__}: {e}).", file=sys.stderr)
        return []

    out = []
    for line in r.text.splitlines()[1:]:
        f = line.rstrip("\n").split("|")
        # r[0]='Y' quotato, r[5]=ETF, r[7]=test issue
        if len(f) < 8 or f[0] != "Y" or f[5] == "Y" or f[7] == "Y":
            continue
        if NOISE.search(f[2]):
            continue
        sym = f[1].strip()
        # Solo ticker semplici: le classi speciali ("BRK.B" -> "BRK-B" su Yahoo) e i
        # simboli con suffisso portano piu' errori che titoli utili in questa lista.
        if not re.fullmatch(r"[A-Z]{1,5}", sym):
            continue
        out.append({"symbol": sym, "name": clean_name(f[2]), "exchange": EXCHANGES.get(f[3], f[3])})
    return out


def chunked(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    listings = load_listings()
    if not listings:
        print("Universo LIVE non aggiornato: si tiene quello esistente.", file=sys.stderr)
        return
    print(f"Listino USA: {len(listings)} societa' (NYSE + Nasdaq + NYSE American).")

    by = {c["symbol"]: c for c in listings}
    symbols = list(by)
    rows, t0 = [], time.time()
    for n, chunk in enumerate(chunked(symbols, CHUNK_SIZE), 1):
        try:
            data = yf.download(chunk, period="2d", group_by="ticker", threads=True,
                               progress=False, auto_adjust=False)
        except Exception as e:
            print(f"  ! batch {n}: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        for sym in chunk:
            try:
                sub = data[sym] if len(chunk) > 1 else data
                closes = sub["Close"].dropna()
                if not len(closes):
                    continue
                price = float(closes.iloc[-1])
                vols = sub["Volume"].dropna()
                dollar_vol = price * (float(vols.iloc[-1]) if len(vols) else 0.0)
                if price >= MIN_PRICE and dollar_vol >= MIN_DOLLAR_VOL:
                    rows.append({**by[sym], "dollar_vol": round(dollar_vol)})
            except Exception:
                continue
        if n % 8 == 0:
            print(f"  batch {n}/{(len(symbols) + CHUNK_SIZE - 1)// CHUNK_SIZE} "
                  f"· {len(rows)} liquidi · {time.time() - t0:.0f}s")

    # Copertura: quanti simboli il fetch ha davvero letto (non quanti hanno passato
    # il filtro). Si stima dai batch andati a buon fine.
    if len(rows) < 100:
        print(f"ATTENZIONE: solo {len(rows)} titoli liquidi trovati: fetch probabilmente "
              f"limitato. Tengo l'universo esistente.", file=sys.stderr)
        return

    rows.sort(key=lambda r: -r["dollar_vol"])
    path = os.path.join(out_dir, OUT_FILE)
    os.makedirs(out_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": time.strftime("%Y-%m-%d"),
            "criteria": {"min_dollar_volume": MIN_DOLLAR_VOL, "min_price": MIN_PRICE},
            "companies": rows,
        }, f, ensure_ascii=False, indent=2)
    print(f"Scritto {path}: {len(rows)} societa' liquide su {len(symbols)} quotate "
          f"({time.time() - t0:.0f}s).")


if __name__ == "__main__":
    main()
