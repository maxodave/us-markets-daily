"""Scrive streaks.json: da quanti giorni di fila ogni societa' chiude in rialzo
o in ribasso, piu' i conteggi d'insieme.

A cosa serve. L'edizione racconta UNA seduta: chi e' salito e chi e' scceso ieri.
Questo file racconta la PERSISTENZA, che e' un'altra domanda e non si legge nella
tabella del giorno: quante societa' stanno salendo da tre giorni di fila, quante
scendono da cinque, e chi ha la serie piu' lunga in corso.

DA DOVE VENGONO I DATI, e perche' non dall'archivio. Le edizioni in editions/
conservano solo i primi e gli ultimi dieci titoli piu' le statistiche
d'insieme: non c'e' la variazione giornaliera di OGNI societa', quindi le serie
non si possono ricostruire da li'. Si ricalcolano dalle barre giornaliere di
Yahoo, che e' anche meglio: la storia disponibile non e' limitata ai giorni in
cui il sito e' esistito.

COME SI CONTA UNA SERIE. Chiusura contro chiusura precedente, partendo
dall'ultima barra e andando indietro:
  - chiusura piu' alta della precedente  -> giorno "su"
  - piu' bassa                            -> giorno "giu'"
  - identica                              -> la serie si INTERROMPE
Una chiusura identica al centesimo e' raria e non e' ne' un rialzo ne' un
ribasso: contarla come uno dei due allungherebbe una serie che non c'e'.

La serie e' quella IN CORSO, cioe' quella che finisce sull'ultima seduta
disponibile. Non e' la serie piu' lunga mai fatta dalla societa': quella
risponderebbe a una domanda diversa ("il record storico") e si confonderebbe con
questa nella stessa tabella.

Uso:  python3 fetch_streaks.py [cartella_output]
      (default: cartella corrente -> streaks.json)
"""
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone

import yfinance as yf

UNIVERSE_FILE = "universe.json"
# Quanto passato scaricare. Tre mesi sono ~62 sedute: abbondano per qualsiasi
# serie plausibile (oltre i dieci giorni di fila si entra nell'aneddotico) e
# restano leggeri da scaricare per 558 titoli.
PERIOD = "3mo"
CHUNK_SIZE = 80          # come fetch_data.py: batch per non farsi limitare da Yahoo
TOP_N = 15               # quante societa' mostrare in ciascuna delle due classifiche
# Sotto questa copertura il quadro d'insieme sarebbe fuorviante (i conteggi
# sembrerebbero piccoli solo perche' meta' dei titoli non ha risposto): meglio
# non scrivere il file che pubblicare numeri che non descrivono il mercato.
MIN_COVERAGE = 0.7


def chunked(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def load_universe(base_dir: str) -> list[dict]:
    """Le societa' dei tre indici, normalizzate a {yf_symbol, symbol, name}."""
    for path in (os.path.join(base_dir, UNIVERSE_FILE), UNIVERSE_FILE):
        try:
            with open(path, encoding="utf-8") as f:
                companies = json.load(f).get("companies", [])
        except (FileNotFoundError, ValueError):
            continue
        if companies:
            return [
                {
                    "yf_symbol": c.get("yf_symbol") or c["symbol"],
                    "symbol": c["symbol"],
                    "name": c.get("name", ""),
                    # Serve alla pagina per marcare le righe della borsa di Milano:
                    # universe.json tiene insieme i tre indici USA e il FTSE MIB, e
                    # una classifica che li mescola senza dirlo si legge male.
                    "indices": c.get("indices") or [],
                }
                for c in companies
            ]
    return []


def streak_of(closes) -> tuple[int, float] | None:
    """La serie IN CORSO: (giorni, variazione % cumulata sulla serie).

    Segno positivo = giorni di rialzo consecutivi, negativo = di ribasso.
    None se non ci sono almeno due chiusure, o se l'ultima seduta e' invariata
    (nessuna serie in corso, vedi il docstring del modulo).
    """
    v = [float(x) for x in closes]
    if len(v) < 2:
        return None
    verso = 0
    if v[-1] > v[-2]:
        verso = 1
    elif v[-1] < v[-2]:
        verso = -1
    else:
        return None

    giorni = 0
    i = len(v) - 1
    while i > 0:
        if verso == 1 and v[i] > v[i - 1]:
            giorni += 1
        elif verso == -1 and v[i] < v[i - 1]:
            giorni += 1
        else:
            break
        i -= 1

    # Variazione cumulata: dalla chiusura PRIMA che la serie iniziasse a oggi.
    partenza = v[len(v) - 1 - giorni]
    cumulata = (v[-1] / partenza - 1) * 100 if partenza else 0.0
    return (giorni * verso, round(cumulata, 2))


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    universe = load_universe(out_dir)
    if not universe:
        print("Nessun universo: manca universe.json. Non scrivo niente.", file=sys.stderr)
        return 1
    print(f"  universo: {len(universe)} societa' dei tre indici.")

    by_symbol = {c["yf_symbol"]: c for c in universe}
    simboli = list(by_symbol)
    righe = []
    ultima_barra = []

    for chunk in chunked(simboli, CHUNK_SIZE):
        try:
            data = yf.download(
                chunk, period=PERIOD, group_by="ticker", threads=True,
                progress=False, auto_adjust=False,
            )
        except Exception as e:
            print(f"  ! batch: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        for sym in chunk:
            try:
                serie = (data["Close"] if len(chunk) == 1 else data[sym]["Close"]).dropna()
                if len(serie) < 2:
                    continue
                s = streak_of(serie.values)
                if s is None:
                    righe.append({"symbol": by_symbol[sym]["symbol"], "name": by_symbol[sym]["name"],
                                  "indices": by_symbol[sym]["indices"], "days": 0, "cum_pct": 0.0})
                else:
                    giorni, cum = s
                    righe.append({"symbol": by_symbol[sym]["symbol"], "name": by_symbol[sym]["name"],
                                  "indices": by_symbol[sym]["indices"], "days": giorni, "cum_pct": cum})
                ultima_barra.append(serie.index[-1].strftime("%Y-%m-%d"))
            except Exception:
                continue

    coverage = len(righe) / max(1, len(simboli))
    print(f"  serie calcolate: {len(righe)}/{len(simboli)} ({coverage:.0%} di copertura).")
    if coverage < MIN_COVERAGE:
        print("  ! copertura troppo bassa: non scrivo il file (i conteggi sarebbero fuorvianti).",
              file=sys.stderr)
        return 1

    # La seduta di riferimento e' la data piu' RICORRENTE fra le ultime barre, non
    # quella di un singolo titolo: come in fetch_data.py, un titolo con la barra
    # vecchia non deve decidere la data di tutti.
    session_date = Counter(ultima_barra).most_common(1)[0][0] if ultima_barra else None

    su = [r for r in righe if r["days"] > 0]
    giu = [r for r in righe if r["days"] < 0]
    fermi = [r for r in righe if r["days"] == 0]

    def distribuzione(gruppo):
        """Quante societa' per lunghezza di serie. Le serie molto lunghe si
        raccolgono in "8+": tenerle separate darebbe righe da una societa'."""
        c = Counter(min(abs(r["days"]), 8) for r in gruppo)
        return {("8+" if k == 8 else str(k)): c[k] for k in sorted(c)}

    data_out = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "session_date": session_date,
        "universe": len(righe),
        "up": {
            "count": len(su),
            "by_length": distribuzione(su),
            "top": sorted(su, key=lambda r: (-r["days"], -r["cum_pct"]))[:TOP_N],
        },
        "down": {
            "count": len(giu),
            "by_length": distribuzione(giu),
            "top": sorted(giu, key=lambda r: (r["days"], r["cum_pct"]))[:TOP_N],
        },
        "flat": {"count": len(fermi)},
    }

    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "streaks.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data_out, f, ensure_ascii=False, indent=2)

    piu_lunga_su = max((r["days"] for r in su), default=0)
    piu_lunga_giu = min((r["days"] for r in giu), default=0)
    print(f"  in rialzo da almeno un giorno: {len(su)} · in ribasso: {len(giu)} · invariate: {len(fermi)}")
    print(f"  serie piu' lunga: +{piu_lunga_su} giorni / {piu_lunga_giu} giorni")
    print(f"Scritto {path} (seduta {session_date}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
