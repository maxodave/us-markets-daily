"""
Prepara l'edizione del giorno per la pubblicazione, a partire da
editions/YYYY-MM-DD.json. Produce tre file in publish/:

  YYYY-MM-DD-newsletter.html  -> da INCOLLARE nell'editor Substack
  YYYY-MM-DD-newsletter.md    -> stessa cosa in markdown (archivio/altri usi)
  YYYY-MM-DD-linkedin.txt     -> bozza del post LinkedIn che rimanda all'edizione

Caratteristiche volute (vedi newsletter/TEMPLATE.md):
  - lingua inglese, tono analitico: fatti, numeri, fonti citate;
  - nessuna immagine (solo testo e link): niente questioni di licenza sulle
    copertine delle testate su un sito pubblico;
  - nessun linguaggio predittivo o di raccomandazione;
  - disclaimer sempre presente.

L'HTML e' volutamente "semantico e nudo" (h2/p/ul/li/a/hr/strong): Substack
scarta il CSS personalizzato ma conserva la struttura quando incolli.

Questo script NON pubblica nulla: la pubblicazione resta un tuo gesto.

Uso:
    python3 build_publish.py                 # ultima edizione disponibile
    python3 build_publish.py 2026-08-05      # edizione specifica
"""
import glob
import html
import json
import os
import sys
from datetime import datetime

from mover_reason import pick_reason

EDITIONS_DIR = "editions"
OUT_DIR = "publish"
MAX_MOVERS = 6
# Pagina pubblica (build_public_page.py), su GitHub Pages. La rigenera ogni notte
# un GitHub Action nel repo pubblico, indipendente da questo Mac.
SITE_URL = "https://maxodave.github.io/us-markets-daily/"

MONTHS_EN = {
    1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June",
    7: "July", 8: "August", 9: "September", 10: "October", 11: "November", 12: "December",
}

DISCLAIMER = (
    "This newsletter reports on publicly available market news for informational and "
    "educational purposes only. It does not constitute investment, financial, or trading "
    "advice. Always do your own research."
)
HASHTAGS = "#StockMarket #SP500 #Markets #Earnings #WallStreet"


def english_date(date_str: str) -> str:
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return f"{MONTHS_EN[d.month]} {d.day}, {d.year}"
    except Exception:
        return date_str or "n/d"


def english_day_month(date_str: str) -> str:
    """Es. '2026-08-05' -> 'August 5' (senza anno: la riga dice "yesterday")."""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return f"{MONTHS_EN[d.month]} {d.day}"
    except Exception:
        return date_str or "n/d"


def edition_number(edition_date: str) -> int:
    """Numero progressivo dell'edizione (#001, #002, ...).

    Contato sull'archivio in editions/: quante edizioni esistono fino a questa
    inclusa. Non e' un contatore salvato da qualche parte, cosi' non puo'
    disallinearsi dall'archivio reale; se un giorno si rigenera un'edizione
    passata il suo numero resta quello giusto.
    """
    dates = []
    for p in glob.glob(os.path.join(EDITIONS_DIR, "*.json")):
        name = os.path.basename(p)[: -len(".json")]
        dates.append(name)
    dates = sorted(d for d in dates if d <= edition_date)
    return len(dates) if dates else 1


def fmt_pct(v: float) -> str:
    return f"{'+' if v > 0 else ''}{v:.2f}%"


NO_CATALYST = " — no company-specific catalyst reported by the outlets tracked."


def mover_bullet(m: dict) -> str:
    """Riga del mover nel post/newsletter. L'edizione porta gia' la motivazione
    scelta da build_edition.py: la si riusa, cosi' post e sito citano la stessa
    notizia. Il fallback su pick_reason() serve per le edizioni salvate prima che
    il campo esistesse."""
    reason = m.get("reason") or pick_reason(m)
    base = f"{m['name']} ({m['symbol']}) {fmt_pct(m['pct_change'])}"
    if not reason:
        return base + NO_CATALYST
    source = reason.get("source")
    return base + f" — {reason['title']}" + (f" ({source})" if source else "")


def build_sections(ed: dict) -> dict:
    # Il post copre TUTTI E TRE gli indici, quindi legge il blocco "combined":
    # l'unione deduplicata di S&P 500, Dow Jones e Nasdaq-100. Cambiare solo le
    # parole ("US markets" al posto di "S&P 500") lasciando i conteggi del solo
    # S&P 500 direbbe una cosa falsa — il testo e i numeri devono coprire lo
    # stesso perimetro. Le edizioni pubblicate prima della modifica multi-indice
    # non hanno questo blocco: per loro si ricade sul vecchio auto_report, che era
    # S&P 500, ed e' corretto cosi' perche' quel giorno il sito copriva solo quello.
    by_index = ed.get("auto_report_by_index") or {}
    report = by_index.get("combined") or ed["auto_report"]
    covers_all_markets = "combined" in by_index

    stats = report["stats"]
    gainers = report["gainers"][:MAX_MOVERS]
    losers = report["losers"][:MAX_MOVERS]
    # "US markets" solo quando i numeri lo sono davvero. L'articolo e' incluso nella
    # stringa: "across US markets" non lo vuole, "across the S&P 500" si'.
    universe = "US-listed" if covers_all_markets else "S&P 500"
    scope = "US markets" if covers_all_markets else "the S&P 500"

    session_en = english_date(ed["session_date"])
    edition_en = english_date(ed["edition_date"])

    if stats["n_up"] > stats["n_down"] * 1.5:
        breadth = "Breadth was clearly positive"
    elif stats["n_down"] > stats["n_up"] * 1.5:
        breadth = "Breadth was clearly negative"
    else:
        breadth = "Breadth was mixed"

    best = ", ".join(f"{s['sector']} ({fmt_pct(s['avg_pct'])})" for s in stats["best_sectors"])
    worst = ", ".join(f"{s['sector']} ({fmt_pct(s['avg_pct'])})" for s in stats["worst_sectors"])

    top = gainers[0] if gainers else None
    headline = f"US Markets Daily — {edition_en}"
    if top:
        headline += f": {top['name']} {fmt_pct(top['pct_change'])} Leads {scope}"

    # Titolo e sottotitolo per Substack, che li tiene in due campi separati (a
    # differenza di LinkedIn, dove il titolo e' la prima riga del testo).
    # Il sottotitolo NON nomina un indice: il sito copre S&P 500, Dow Jones e
    # Nasdaq-100, quindi dire "S&P 500 session" sarebbe piu' stretto della realta'.
    substack_title = f"🇺🇸US Markets Daily — {edition_en} #{edition_number(ed['edition_date']):03d}"
    tone = {
        "Breadth was clearly positive": "a broadly positive",
        "Breadth was clearly negative": "a broadly negative",
    }.get(breadth, "a mixed")
    substack_subtitle = (
        f"{top['name']} {fmt_pct(top['pct_change'])} leads {tone} session across {scope}"
        if top
        else f"{tone.capitalize()} session across {scope}"
    )

    summary = (
        f"In the {session_en} session, {stats['n_up']} {universe} companies closed higher and "
        f"{stats['n_down']} closed lower out of {stats['n_total']} tracked across the S&P 500, "
        f"Dow Jones and Nasdaq-100, for an average move of "
        f"{fmt_pct(stats['avg_pct'])}. {breadth}. Strongest sectors by average move: {best}. "
        f"Weakest: {worst}."
        if covers_all_markets
        else
        f"In the {session_en} session, {stats['n_up']} S&P 500 companies closed higher and "
        f"{stats['n_down']} closed lower out of {stats['n_total']} tracked, for an average move of "
        f"{fmt_pct(stats['avg_pct'])}. {breadth}. Strongest sectors by average move: {best}. "
        f"Weakest: {worst}."
    )

    # Solo le testate effettivamente CITATE nei bullet, non tutte quelle sfiorate
    # durante la raccolta: la riga "Sources" deve corrispondere a cio' che si legge.
    sources = sorted({
        r["source"]
        for r in ((m.get("reason") or pick_reason(m)) for m in gainers + losers)
        if r and r.get("source")
    })

    return {
        "headline": headline,
        "substack_title": substack_title,
        "substack_subtitle": substack_subtitle,
        "scope": scope,
        "edition_en": edition_en,
        "session_en": session_en,
        "session_en_day_month": english_day_month(ed["session_date"]),
        "number": edition_number(ed["edition_date"]),
        "summary": summary,
        "gainers": gainers,
        "losers": losers,
        "sources": sources,
    }


def render_html(s: dict) -> str:
    e = html.escape

    def ul(movers):
        items = "\n".join(f"    <li>{e(mover_bullet(m))}</li>" for m in movers)
        return f"  <ul>\n{items}\n  </ul>"

    sources_line = (
        f"  <p><em>Sources: {e(', '.join(s['sources']))}.</em></p>\n" if s["sources"] else ""
    )
    # Senza dichiarare la codifica, un browser che apre questo file da solo (per
    # copiarne il contenuto formattato, come si fa per incollarlo in Substack)
    # indovina la codifica sbagliata e trasforma —/'/" in mojibake (â€", â€™...).
    # Substack scarta comunque questo <meta> quando il frammento viene incollato:
    # non introduce CSS ne' struttura visibile, serve solo a far leggere il file
    # correttamente a chi lo apre per copiarlo.
    return f"""<meta charset="utf-8">
<h1>{e(s['headline'])}</h1>

<p>{e(s['summary'])}</p>

<h2>Top Gainers</h2>
{ul(s['gainers'])}

<h2>Top Decliners</h2>
{ul(s['losers'])}

<hr>

{sources_line}  <p><em>{e(DISCLAIMER)}</em></p>

<p>{e(HASHTAGS)}</p>
"""


def render_markdown(s: dict) -> str:
    def bullets(movers):
        return "\n".join(f"- **{mover_bullet(m)}**" for m in movers)

    sources_line = f"*Sources: {', '.join(s['sources'])}.*\n\n" if s["sources"] else ""
    return f"""# {s['headline']}

{s['summary']}

## Top Gainers

{bullets(s['gainers'])}

## Top Decliners

{bullets(s['losers'])}

---

{sources_line}*{DISCLAIMER}*

{HASHTAGS}
"""


def render_substack(s: dict) -> str:
    """Corpo del post Substack, pronto da incollare — SOLO il corpo.

    Titolo e sottotitolo restano fuori: su Substack stanno in due campi propri,
    e includerli qui produrrebbe il titolo doppio (una volta nel campo, una
    volta dentro l'articolo). Vengono stampati a parte da main() e finiscono
    nell'email, da copiare nei rispettivi campi.

    Rispetto a render_html() (che serve alla newsletter "archivio"):
      - niente <h1>/<h2>: "📈 Top Gainers" e' un paragrafo con emoji, come nelle
        edizioni gia' pubblicate, non un'intestazione;
      - l'URL finale e' un <a href> VERO. Incollato come testo semplice Substack
        non lo trasforma in link e il lettore non puo' cliccarlo — era cosi'
        nell'edizione #003 prima di questa correzione;
      - <meta charset> in testa: senza, il browser da cui si copia sbaglia la
        codifica e trattini/apostrofi arrivano come mojibake (â€", â€™).
    """
    e = html.escape

    def ul(movers):
        items = "\n".join(f"  <li>{e(mover_bullet(m))}</li>" for m in movers)
        return f"<ul>\n{items}\n</ul>"

    sources_line = (
        f"<p><em>Sources: {e(', '.join(s['sources']))}.</em></p>\n\n" if s["sources"] else ""
    )
    return f"""<meta charset="utf-8">
<p>{e(s['summary'])}</p>

<p>📈 Top Gainers</p>
{ul(s['gainers'])}

<p>📉 Top Decliners</p>
{ul(s['losers'])}

{sources_line}<p><em>{e(DISCLAIMER)}</em></p>

<p>🔗 Tap the link below for a deeper look at {e(s['scope'])} news from
yesterday's session, {e(s['session_en_day_month'])}<br>
<a href="{SITE_URL}">{SITE_URL}</a></p>
"""


def render_linkedin(s: dict) -> str:
    """Post LinkedIn: righe brevi, nessun markdown (LinkedIn non lo interpreta).

    FORMATO FISSO, da non cambiare senza che l'utente lo chieda: e' lo stesso
    identico schema di ogni edizione, cosi' il post e' riconoscibile a colpo
    d'occhio e l'utente non deve riadattarlo a mano ogni mattina. Nell'ordine:

        🇺🇸 titolo · data · numero progressivo edizione
        riassunto della seduta
        📈 Top Gainers   (elenco COMPLETO, una riga per titolo, con la causa)
        📉 Top Decliners (idem)
        disclaimer · hashtag
        🔗 invito al link + URL sulla riga sotto, sempre ultimo

    Cambia solo il contenuto (data, numero, riassunto, movimenti): la
    struttura no. Tutto il post e' in inglese, invito finale compreso.

    L'URL va sulla riga DOPO il testo, perche' il testo dice "below".
    """
    lines = [
        f"🇺🇸 US Markets Daily — {s['edition_en']} #{s['number']:03d}",
        "",
        s["summary"],
        "",
        "📈 Top Gainers",
    ]
    lines += [f"• {mover_bullet(m)}" for m in s["gainers"]]
    lines += ["", "📉 Top Decliners"]
    lines += [f"• {mover_bullet(m)}" for m in s["losers"]]
    lines += [
        "",
        DISCLAIMER,
        "",
        HASHTAGS,
        "",
        f"🔗 Tap the link below for a deeper look at {s['scope']} news from "
        f"yesterday's session, {s['session_en_day_month']}",
        SITE_URL,
    ]
    body = "\n".join(lines)

    note = """# ----------------------------------------------------------------------
# BOZZA POST LINKEDIN — rileggila e pubblicala tu (nulla viene postato da qui).
#
# Il link in fondo punta alla pagina pubblica (su GitHub Pages), che si aggiorna
# da sola ogni notte tramite GitHub Actions: quando leggi questa bozza la pagina
# mostra gia' l'edizione di oggi (vedi README).
#
# Le righe che iniziano con # sono queste istruzioni: NON copiarle nel post.
# ----------------------------------------------------------------------

"""
    return note + body + "\n"


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    if len(sys.argv) > 1:
        path = os.path.join(EDITIONS_DIR, f"{sys.argv[1]}.json")
        if not os.path.exists(path):
            print(f"ERRORE: edizione non trovata: {path}", file=sys.stderr)
            sys.exit(1)
    else:
        candidates = sorted(glob.glob(os.path.join(EDITIONS_DIR, "*.json")))
        if not candidates:
            print(f"ERRORE: nessuna edizione in {EDITIONS_DIR}/ (esegui build_edition.py)", file=sys.stderr)
            sys.exit(1)
        path = candidates[-1]

    with open(path) as f:
        ed = json.load(f)

    s = build_sections(ed)
    stem = os.path.join(OUT_DIR, ed["edition_date"])

    with open(f"{stem}-newsletter.html", "w", encoding="utf-8") as f:
        f.write(render_html(s))
    with open(f"{stem}-newsletter.md", "w", encoding="utf-8") as f:
        f.write(render_markdown(s))
    with open(f"{stem}-linkedin.txt", "w", encoding="utf-8") as f:
        f.write(render_linkedin(s))
    with open(f"{stem}-substack.html", "w", encoding="utf-8") as f:
        f.write(render_substack(s))

    print(f"Pronti per la pubblicazione (edizione {ed['edition_date']}, seduta {s['session_en']}):")
    print(f"  {stem}-substack.html     <- APRI questo nel browser e incollalo in Substack")
    print(f"  {stem}-linkedin.txt      <- bozza post LinkedIn")
    print(f"  {stem}-newsletter.html   <- versione con titolo incorporato (archivio)")
    print(f"  {stem}-newsletter.md     <- versione markdown (archivio)")
    print("\n--- Da copiare nei due campi in cima all'editor Substack ---")
    print(f"Titolo:      {s['substack_title']}")
    print(f"Sottotitolo: {s['substack_subtitle']}")
    print("\nNessuna pubblicazione automatica: rileggi e pubblica tu.")


if __name__ == "__main__":
    main()
