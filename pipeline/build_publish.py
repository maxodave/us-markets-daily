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

import weekend_edition
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
# L'edizione senza seduta parla d'altro: ripetere #SP500 e #Earnings su un post
# che non contiene ne' l'uno ne' le altre porta il lettore sbagliato.
WEEKEND_HASHTAGS = "#StockMarket #Markets #WallStreet #WeekAhead #Crypto"


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


def fmt_signal(inst: dict) -> str:
    return f"{inst['name_en']} {fmt_pct(inst['pct_change'])}"


def build_weekend_sections(ed: dict) -> dict:
    """Il post delle edizioni SENZA seduta nuova (domenica, lunedi', post-festivi).

    Stessa struttura fissa del post quotidiano — titolo, riassunto, due o tre
    elenchi, disclaimer, hashtag, link in fondo — ma con un contenuto che non
    ripete nulla: le notizie del giorno appena passato al posto dei mover, le
    quotazioni dei mercati rimasti aperti al posto delle percentuali di seduta.
    Vedi weekend_edition.py per il perche'.

    Il testo del riassunto e' quello DETERMINISTICO dell'edizione, non il
    commento scritto dal modello: e' la stessa scelta gia' fatta per il post
    quotidiano, cosi' il post esce identico a se stesso anche le notti in cui
    l'API non risponde.
    """
    w = ed["weekend_report"]
    paragraphs = (w.get("paragraphs") or {}).get("en") or []
    edition_en = english_date(ed["edition_date"])

    signal_groups = [
        {
            "label": g["label"]["en"],
            "line": " · ".join(fmt_signal(i) for i in g["instruments"]),
        }
        for g in (w.get("signals") or {}).get("groups", [])
    ]

    # La newsletter e' in inglese (vedi newsletter/TEMPLATE.md): fuori dal tema
    # "Italia" i titoli in italiano restano sul sito — che ha il pulsante lingua —
    # ma non nel post. Un elenco inglese con due righe in italiano in mezzo e' la
    # prima cosa che un lettore nota, e non e' quella che deve notare.
    digest = []
    for s in w.get("sections", []):
        items = [
            {"title": strip_title(i["title"]), "source": i["source"]}
            for i in s["items"]
            if s["key"] == "italia" or not weekend_edition.is_italian_source(i["source"])
        ][:MAX_WEEKEND_PER_THEME]
        if items:
            digest.append({"label": s["label"]["en"], "items": items})

    lead = (w.get("lead_headlines") or [{}])[0]
    subtitle = (
        f"{w['covers_date_en']}: {lead['title']}" if lead.get("title")
        else f"The weekend's news, and what to watch at the next open"
    )

    niche = [
        {
            "symbol": s["symbol"], "name": s["name"], "score": s["score"],
            "title": strip_title(s["title"]), "source": s["source"],
        }
        for s in (w.get("niche_signals") or [])
    ]

    sources = sorted({
        i["source"] for d in digest for i in d["items"] if i.get("source")
    } | {w_["source"] for w_ in (w.get("watchlist") or []) if w_.get("source")}
      | {n["source"] for n in niche if n.get("source")})

    return {
        "kind": "weekend",
        "headline": f"US Markets Weekend — {edition_en}",
        "substack_title": f"🇺🇸US Markets Weekend — {edition_en} #{edition_number(ed['edition_date']):03d}",
        # Il sottotitolo non promette numeri di seduta: e' il primo posto in cui
        # un lettore verificherebbe se il post di domenica e' un doppione.
        "substack_subtitle": subtitle[:180],
        "edition_en": edition_en,
        "covers_en": w["covers_date_en"],
        "number": edition_number(ed["edition_date"]),
        "summary": paragraphs[0] if paragraphs else "",
        "digest": digest,
        "signal_groups": signal_groups,
        "watchlist": [
            {"title": strip_title(x["title"]), "source": x["source"]}
            for x in (w.get("watchlist") or [])
        ],
        "niche_signals": niche,
        "sources": sources,
    }


# Quante notizie per tema nel post. Meno che sul sito: un post di LinkedIn con
# ventiquattro righe non lo legge nessuno, e il link in fondo porta al resto.
MAX_WEEKEND_PER_THEME = 3


def strip_title(title: str) -> str:
    t = (title or "").strip()
    return t.rsplit(" - ", 1)[0].strip() if " - " in t else t


def build_sections(ed: dict) -> dict:
    if ed.get("edition_kind") == "weekend_recap" and ed.get("weekend_report"):
        return build_weekend_sections(ed)

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
        "kind": "session",
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


# Testi condivisi dalle quattro rese del post del fine settimana, cosi' la stessa
# frase non esiste in quattro copie che prima o poi divergono.
W_DIGEST_LABEL = "📰 The weekend in headlines"
W_SIGNALS_LABEL = "🌙 What traded while Wall Street was closed"
W_SIGNALS_NOTE = (
    "Change since Friday's US close. These are quotes on markets that stay open, "
    "not forecasts for the coming session."
)
W_WATCH_LABEL = "👀 On the calendar"
W_WATCH_NOTE = (
    "Scheduled events and previews published by the outlets themselves — listed, not predicted."
)
W_NICHE_LABEL = "🔎 Named in weekend coverage"
W_NICHE_NOTE = (
    "A lexical score (0-10) for how intensely the outlets themselves wrote about it — "
    "not a forecast, not investment advice, and not backtested against real price moves."
)
W_NO_SESSION_NOTE = (
    "No new trading session: the last one was covered in the previous edition and its "
    "figures are not repeated here."
)


def weekend_headline_line(item: dict) -> str:
    return f"{item['title']} ({item['source']})" if item.get("source") else item["title"]


def niche_signal_line(item: dict) -> str:
    return f"{item['name']} ({item['symbol']}, {item['score']}/10) — {item['source']}: {item['title']}"


def render_html_weekend(s: dict) -> str:
    e = html.escape

    def ul(items):
        rows = "\n".join(f"    <li>{e(x)}</li>" for x in items)
        return f"  <ul>\n{rows}\n  </ul>"

    blocks = [f"<h1>{e(s['headline'])}</h1>", f"<p>{e(s['summary'])}</p>"]
    if s["digest"]:
        blocks.append(f"<h2>{e(W_DIGEST_LABEL)}</h2>")
        for d in s["digest"]:
            blocks.append(f"  <p><strong>{e(d['label'])}</strong></p>")
            blocks.append(ul(weekend_headline_line(i) for i in d["items"]))
    if s["signal_groups"]:
        blocks.append(f"<h2>{e(W_SIGNALS_LABEL)}</h2>")
        blocks.append(ul(f"{g['label']}: {g['line']}" for g in s["signal_groups"]))
        blocks.append(f"  <p><em>{e(W_SIGNALS_NOTE)}</em></p>")
    if s["niche_signals"]:
        blocks.append(f"<h2>{e(W_NICHE_LABEL)}</h2>")
        blocks.append(ul(niche_signal_line(i) for i in s["niche_signals"]))
        blocks.append(f"  <p><em>{e(W_NICHE_NOTE)}</em></p>")
    if s["watchlist"]:
        blocks.append(f"<h2>{e(W_WATCH_LABEL)}</h2>")
        blocks.append(ul(weekend_headline_line(i) for i in s["watchlist"]))
        blocks.append(f"  <p><em>{e(W_WATCH_NOTE)}</em></p>")
    blocks.append("<hr>")
    if s["sources"]:
        blocks.append(f"  <p><em>Sources: {e(', '.join(s['sources']))}.</em></p>")
    blocks.append(f"  <p><em>{e(DISCLAIMER)}</em></p>")
    blocks.append(f"<p>{e(WEEKEND_HASHTAGS)}</p>")
    return '<meta charset="utf-8">\n' + "\n\n".join(blocks) + "\n"


def render_markdown_weekend(s: dict) -> str:
    out = [f"# {s['headline']}", "", s["summary"], ""]
    if s["digest"]:
        out += [f"## {W_DIGEST_LABEL}", ""]
        for d in s["digest"]:
            out.append(f"**{d['label']}**")
            out += [f"- {weekend_headline_line(i)}" for i in d["items"]]
            out.append("")
    if s["signal_groups"]:
        out += [f"## {W_SIGNALS_LABEL}", ""]
        out += [f"- **{g['label']}**: {g['line']}" for g in s["signal_groups"]]
        out += ["", f"*{W_SIGNALS_NOTE}*", ""]
    if s["niche_signals"]:
        out += [f"## {W_NICHE_LABEL}", ""]
        out += [f"- {niche_signal_line(i)}" for i in s["niche_signals"]]
        out += ["", f"*{W_NICHE_NOTE}*", ""]
    if s["watchlist"]:
        out += [f"## {W_WATCH_LABEL}", ""]
        out += [f"- {weekend_headline_line(i)}" for i in s["watchlist"]]
        out += ["", f"*{W_WATCH_NOTE}*", ""]
    out += ["---", ""]
    if s["sources"]:
        out += [f"*Sources: {', '.join(s['sources'])}.*", ""]
    out += [f"*{DISCLAIMER}*", "", WEEKEND_HASHTAGS, ""]
    return "\n".join(out)


def render_substack_weekend(s: dict) -> str:
    """Corpo del post Substack del fine settimana — SOLO il corpo.

    Stesse regole del post quotidiano (vedi render_substack): niente h1/h2, il
    link finale come <a href> vero, <meta charset> in testa per chi apre il file
    dal browser per copiarlo.
    """
    e = html.escape

    def ul(items):
        rows = "\n".join(f"  <li>{e(x)}</li>" for x in items)
        return f"<ul>\n{rows}\n</ul>"

    blocks = [f"<p>{e(s['summary'])}</p>"]
    if s["digest"]:
        blocks.append(f"<p>{e(W_DIGEST_LABEL)}</p>")
        for d in s["digest"]:
            blocks.append(f"<p><strong>{e(d['label'])}</strong></p>")
            blocks.append(ul(weekend_headline_line(i) for i in d["items"]))
    if s["signal_groups"]:
        blocks.append(f"<p>{e(W_SIGNALS_LABEL)}</p>")
        blocks.append(ul(f"{g['label']}: {g['line']}" for g in s["signal_groups"]))
        blocks.append(f"<p><em>{e(W_SIGNALS_NOTE)}</em></p>")
    if s["niche_signals"]:
        blocks.append(f"<p>{e(W_NICHE_LABEL)}</p>")
        blocks.append(ul(niche_signal_line(i) for i in s["niche_signals"]))
        blocks.append(f"<p><em>{e(W_NICHE_NOTE)}</em></p>")
    if s["watchlist"]:
        blocks.append(f"<p>{e(W_WATCH_LABEL)}</p>")
        blocks.append(ul(weekend_headline_line(i) for i in s["watchlist"]))
        blocks.append(f"<p><em>{e(W_WATCH_NOTE)}</em></p>")
    if s["sources"]:
        blocks.append(f"<p><em>Sources: {e(', '.join(s['sources']))}.</em></p>")
    blocks.append(f"<p><em>{e(DISCLAIMER)}</em></p>")
    blocks.append(
        f'<p>🔗 Tap the link below for the full weekend read — every story, by theme,'
        f' plus the markets that stayed open<br>\n<a href="{SITE_URL}">{SITE_URL}</a></p>'
    )
    return '<meta charset="utf-8">\n' + "\n\n".join(blocks) + "\n"


def render_linkedin_weekend(s: dict) -> str:
    """Post LinkedIn del fine settimana: stesso schema fisso di quello quotidiano.

        🇺🇸 titolo · data · numero progressivo edizione
        riassunto (dice esplicitamente che non c'e' una seduta nuova)
        📰 le notizie, per tema
        🌙 cosa ha scambiato a borse chiuse
        🔎 societa' nominate nella copertura del weekend (punteggio lessicale)
        👀 cosa c'e' in calendario
        disclaimer · hashtag
        🔗 invito al link + URL sulla riga sotto, sempre ultimo
    """
    lines = [f"🇺🇸 US Markets Weekend — {s['edition_en']} #{s['number']:03d}", "", s["summary"], ""]
    if s["digest"]:
        lines.append(W_DIGEST_LABEL)
        for d in s["digest"]:
            lines.append(f"{d['label']}:")
            lines += [f"• {weekend_headline_line(i)}" for i in d["items"]]
        lines.append("")
    if s["signal_groups"]:
        lines.append(W_SIGNALS_LABEL)
        lines += [f"• {g['label']}: {g['line']}" for g in s["signal_groups"]]
        lines += [W_SIGNALS_NOTE, ""]
    if s["niche_signals"]:
        lines.append(W_NICHE_LABEL)
        lines += [f"• {niche_signal_line(i)}" for i in s["niche_signals"]]
        lines += [W_NICHE_NOTE, ""]
    if s["watchlist"]:
        lines.append(W_WATCH_LABEL)
        lines += [f"• {weekend_headline_line(i)}" for i in s["watchlist"]]
        lines += [W_WATCH_NOTE, ""]
    lines += [
        DISCLAIMER,
        "",
        WEEKEND_HASHTAGS,
        "",
        "🔗 Tap the link below for the full weekend read — every story, by theme, "
        "plus the markets that stayed open",
        SITE_URL,
    ]
    note = """# ----------------------------------------------------------------------
# BOZZA POST LINKEDIN (edizione del fine settimana, senza seduta nuova) —
# rileggila e pubblicala tu: nulla viene postato da qui.
#
# Questo post NON ripete le percentuali della seduta gia' uscita: e' il
# riassunto delle notizie del giorno appena passato piu' i mercati rimasti
# aperti. Vedi weekend_edition.py.
#
# Le righe che iniziano con # sono queste istruzioni: NON copiarle nel post.
# ----------------------------------------------------------------------

"""
    return note + "\n".join(lines) + "\n"


def render_html(s: dict) -> str:
    if s.get("kind") == "weekend":
        return render_html_weekend(s)
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
    if s.get("kind") == "weekend":
        return render_markdown_weekend(s)

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
    if s.get("kind") == "weekend":
        return render_substack_weekend(s)
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
    if s.get("kind") == "weekend":
        return render_linkedin_weekend(s)
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

    what = (
        f"notizie del {s['covers_en']}, nessuna seduta nuova"
        if s.get("kind") == "weekend"
        else f"seduta {s['session_en']}"
    )
    print(f"Pronti per la pubblicazione (edizione {ed['edition_date']}, {what}):")
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
