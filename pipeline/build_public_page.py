"""
Genera la pagina pubblica autonoma (index.html) assemblando i tre file di
templates/ con i dati delle edizioni.

    templates/page.html   scheletro: testi fissi, disclaimer, footer
    templates/style.css   tutto l'aspetto
    templates/app.js      le funzioni che disegnano l'edizione dai dati

L'aspetto NON sta piu' in questo file: si modifica in templates/ e si guarda
l'effetto con serve_preview.py (vedi templates/COME-MODIFICARE.md). La pagina
viene ricostruita da zero a ogni run, quindi una modifica grafica vale per
l'edizione di domani e per tutto l'archivio, senza toccare le pagine passate.

Non include MAI: la tabella dei 503 titoli, il pannello "Segnali di mercato",
ne' alcun dato dei singoli titoli oltre a quello gia' pubblico nelle edizioni.
Le immagini restano in hotlink dai server delle testate (fonte e link sempre
visibili), per scelta esplicita dell'utente — vedi README, sezione "Limiti noti".

Uso:
    python3 build_public_page.py [cartella_output]
    python3 build_public_page.py --controlla     # verifica i template, non scrive

(default cartella_output: ~/Sites/us-markets-daily, il repository pubblico
separato spinto su GitHub Pages — vedi README)
"""
import glob
import html
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime

# I template stanno accanto a QUESTO file, non nella cartella da cui si lancia lo
# script: lo stesso build_public_page.py viene eseguito dalla cartella privata,
# dal repo pubblico (pipeline/) e dal runner di GitHub.
HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(HERE, "templates")

EDITIONS_DIR = "editions"
# Percorso del repository pubblico separato (vedi README) — DELIBERATAMENTE fuori
# da Cursor_Projects: un default relativo (es. "../../sito") finirebbe dentro
# questo repo privato, creando un repository git annidato per errore.
DEFAULT_OUT_DIR = os.path.expanduser("~/Sites/us-markets-daily")

PLACEHOLDERS = ("__STYLE_CSS__", "__APP_JS__", "__EDITIONS_JSON__", "__FALLBACK_HTML__",
                "__STREAKS_JSON__", "__SHOTS_JSON__")
# Serie in corso per societa' (fetch_streaks.py) e cartella degli screenshot
# giornalieri. Entrambi FACOLTATIVI: se mancano, la vista "Day by day" dice
# che non ci sono invece di rompersi, e il resto della pagina non se ne accorge.
STREAKS_FILE = "streaks.json"
SHOTS_DIR = "shots"

# Campi che il JavaScript legge davvero (verificato su templates/app.js). Il resto
# non viene incorporato nella pagina: erano oltre la metà del peso, e nessuna riga
# li mostrava. Restano tutti in editions/, che e' l'archivio completo.
# "indices" serve al badge indice nella scheda "Combined" (solo li' si mostra).
MOVER_FIELDS = ("symbol", "name", "sector", "pct_change", "last_close", "reason", "indices")
FEED_FIELDS = ("category", "image", "link", "published", "source", "summary", "title")
# Campi del blocco "weekend_report" che il JavaScript disegna davvero. Il resto
# (feed_leftover, lead_headlines, i conteggi grezzi) e' materiale per costruire
# il testo e per il post: sta nell'archivio in editions/, non nella pagina.
WEEKEND_FIELDS = (
    "covers_date", "covers_date_it", "covers_date_en", "window_hours",
    "n_items", "n_digest", "n_sources", "sections", "watchlist",
    "niche_signals", "signals", "paragraphs",
)
# Nell'archivio serve solo di che giornata si trattava. Le varianti _en mancano
# sulle edizioni pre-bilingue: app.js ricade sull'italiano quando non le trova.
ARCHIVE_FIELDS = (
    "edition_date", "edition_date_it", "edition_date_en",
    "session_date_it", "session_date_en", "headline", "headline_en",
    # Le edizioni senza seduta nuova (vedi weekend_edition.py) vanno etichettate
    # anche in archivio: altrimenti l'elenco mostra "seduta del 14 agosto" su tre
    # righe di fila, che e' la stessa ripetizione, solo spostata piu' in basso.
    "edition_kind", "covers_date_it", "covers_date_en",
)
# Indici per cui esiste una finestra dedicata (vedi build_edition.py). "combined"
# e' l'unione deduplicata dei tre, non un quarto indice a se'.
INDEX_KEYS = ("sp500", "dow", "nasdaq100", "ftsemib", "combined")


class TemplateError(Exception):
    """Errore nei template, con messaggio in italiano per chi sta modificando."""


def load_editions() -> list[dict]:
    editions = []
    for p in glob.glob(os.path.join(EDITIONS_DIR, "*.json")):
        try:
            with open(p, encoding="utf-8") as f:
                ed = json.load(f)
        except Exception as e:
            print(f"  ! edizione non leggibile {p}: {e}")
            continue
        if not ed.get("edition_date"):
            continue
        editions.append(ed)
    editions.sort(key=lambda e: e["edition_date"], reverse=True)
    return editions


def load_streaks() -> dict | None:
    """Le serie in corso, se il file c'e'. None non e' un errore: la pagina lo
    dice al lettore ("si scrivono una volta al giorno, dopo la chiusura")."""
    try:
        with open(STREAKS_FILE, encoding="utf-8") as f:
            d = json.load(f)
    except (FileNotFoundError, ValueError, OSError):
        return None
    return d if isinstance(d, dict) and d.get("up") and d.get("down") else None


def list_shots() -> list[str]:
    """Le date per cui esiste shots/YYYY-MM-DD.png.

    La pagina non puo' sapere da sola quali immagini esistono: se provasse a
    caricarle tutte, le giornate senza screenshot mostrerebbero l'icona di
    immagine rotta. L'elenco lo fa la build, che il disco lo vede.
    """
    try:
        nomi = os.listdir(SHOTS_DIR)
    except (FileNotFoundError, NotADirectoryError, OSError):
        return []
    date = []
    for n in nomi:
        if not n.endswith(".png"):
            continue
        gg = n[: -len(".png")]
        try:
            datetime.strptime(gg, "%Y-%m-%d")
        except ValueError:
            continue          # file estraneo nella cartella: si ignora
        date.append(gg)
    return sorted(date)


def slim_mover(m: dict) -> dict:
    return {k: m[k] for k in MOVER_FIELDS if k in m}


def slim_auto_report_by_index(auto_report_by_index: dict) -> dict:
    """Stessa potatura di slim_mover/ARCHIVE_FIELDS, per ciascuno dei 4 indici.

    I paragrafi sono gia' un dict {en, it}: nessuna potatura necessaria, sono
    poche righe di testo per lingua, non liste di notizie.
    """
    out = {}
    for key in INDEX_KEYS:
        block = auto_report_by_index.get(key)
        if not block:
            continue
        out[key] = {
            "stats": block.get("stats") or {},
            "paragraphs": block.get("paragraphs") or {},
            "gainers": [slim_mover(m) for m in (block.get("gainers") or [])],
            "losers": [slim_mover(m) for m in (block.get("losers") or [])],
        }
    return out


def slim_weekend_edition(ed: dict) -> dict:
    """L'edizione senza seduta nuova, ridotta a cio' che la pagina disegna.

    Qui NON entra nulla di auto_report/auto_report_by_index: sono i numeri della
    seduta gia' pubblicata ieri, e la vista del fine settimana non li mostra per
    scelta (vedi weekend_edition.py). Tenerli nella pagina sarebbe solo peso
    inutile — e la tentazione, un giorno, di ridisegnarli.
    """
    w = ed["weekend_report"]
    return {
        "edition_date": ed.get("edition_date"),
        "edition_date_it": ed.get("edition_date_it"),
        "edition_date_en": ed.get("edition_date_en"),
        "session_date_it": ed.get("session_date_it"),
        "session_date_en": ed.get("session_date_en"),
        "covers_date_it": ed.get("covers_date_it"),
        "covers_date_en": ed.get("covers_date_en"),
        "edition_kind": "weekend_recap",
        "headline": ed.get("headline"),
        "headline_en": ed.get("headline_en"),
        "generated_at": ed.get("generated_at"),
        "weekend_commentary_html": ed.get("weekend_commentary_html"),
        "weekend_commentary_html_en": ed.get("weekend_commentary_html_en"),
        "weekend_report": {k: w[k] for k in WEEKEND_FIELDS if k in w},
        "markets_brief": ed.get("markets_brief"),
        "feed": [
            {k: it[k] for k in FEED_FIELDS if k in it}
            for it in (ed.get("feed") or [])
        ],
    }


def day_stats(ed: dict) -> dict | None:
    """I tre numeri che riassumono una seduta: quante societa' su, quante giu', la
    media. Si prende la vista "combined" (l'unione dei tre indici USA) e, se
    l'edizione e' anteriore al multi-indice, il vecchio auto_report.
    """
    by = ed.get("auto_report_by_index") or {}
    src = (by.get("combined") or by.get("sp500") or ed.get("auto_report") or {})
    st = src.get("stats") or {}
    tre = {k: st[k] for k in ("n_up", "n_down", "avg_pct") if st.get(k) is not None}
    return tre or None


def slim_editions(editions: list[dict]) -> list[dict]:
    """Tiene solo cio' che la pagina mostra.

    L'edizione in testa conserva tutto tranne le liste di notizie per mover (6+3
    per ciascuno dei mover di ciascun indice: il grosso del peso, e la pagina non
    ne mostra nessuna); le precedenti si riducono alla riga d'archivio. Senza
    questo la pagina cresce di parecchio al giorno per contenuti che nessuno vede.
    """
    out = []
    for i, ed in enumerate(editions):
        if i > 0:
            riga = {k: ed[k] for k in ARCHIVE_FIELDS if k in ed}
            # I tre numeri della giornata, per le schede del diario ("Day by day").
            # Solo questi tre e non tutto auto_report: la potatura serve a non far
            # crescere la pagina di un blocco al giorno per contenuti che
            # nell'elenco d'archivio nessuno guarda.
            st = day_stats(ed)
            if st:
                riga["day_stats"] = st
            out.append(riga)
            continue
        if ed.get("edition_kind") == "weekend_recap" and ed.get("weekend_report"):
            out.append(slim_weekend_edition(ed))
            continue
        auto = ed.get("auto_report") or {}
        slim = {
            "edition_date": ed.get("edition_date"),
            "edition_date_it": ed.get("edition_date_it"),
            "session_date_it": ed.get("session_date_it"),
            # La seduta in forma ISO serve all'avviso "seduta chiusa": confronta la
            # seduta raccontata con la data di OGGI a New York per capire se
            # l'edizione nuova e' ancora attesa. Senza questo campo il confronto
            # girava su "undefined", quindi risultava sempre "in attesa" e l'avviso
            # restava acceso anche dopo la pubblicazione. Vedi paintSessionClosed().
            "session_date": ed.get("session_date"),
            "edition_kind": ed.get("edition_kind"),
            # Foto di chiusura della lista LIVE (tutto il mercato USA), congelata
            # da build_edition.py. Vedi liveCloseBox() in app.js.
            "live_close_movers": ed.get("live_close_movers"),
            "headline": ed.get("headline"),
            "generated_at": ed.get("generated_at"),
            "manual_commentary_html": ed.get("manual_commentary_html"),
            "auto_report": {
                "stats": auto.get("stats") or {},
                "paragraphs": auto.get("paragraphs") or [],
                "gainers": [slim_mover(m) for m in (auto.get("gainers") or [])],
                "losers": [slim_mover(m) for m in (auto.get("losers") or [])],
            },
            "markets_brief": ed.get("markets_brief"),
            "feed": [
                {k: it[k] for k in FEED_FIELDS if k in it}
                for it in (ed.get("feed") or [])
            ],
        }
        # Presenti solo sulle edizioni bilingui/multi-indice (da questa modifica in
        # avanti): le edizioni precedenti restano cosi' come sono, e app.js lo sa
        # (controlla "auto_report_by_index" per decidere quale vista disegnare).
        if ed.get("auto_report_by_index"):
            slim["edition_date_en"] = ed.get("edition_date_en")
            slim["session_date_en"] = ed.get("session_date_en")
            slim["headline_en"] = ed.get("headline_en")
            slim["manual_commentary_html_en"] = ed.get("manual_commentary_html_en")
            slim["auto_report_by_index"] = slim_auto_report_by_index(ed["auto_report_by_index"])
        out.append(slim)
    return out


def fallback_html(editions: list[dict]) -> str:
    """Testo statico dentro #editionsContent, sostituito dal JS quando funziona.

    Se app.js va in errore il lettore vede almeno di che giornata si tratta; e
    Google e la card di LinkedIn trovano un testo senza eseguire il JavaScript.

    Preferisce l'inglese (lingua primaria del sito) quando l'edizione lo prevede;
    le edizioni precedenti, solo italiane, restano il fallback naturale.
    """
    if not editions:
        return '<div class="no-edition">No edition published yet.</div>'
    ed = editions[0]
    e = html.escape

    by_index = ed.get("auto_report_by_index")
    if ed.get("edition_kind") == "weekend_recap" and ed.get("weekend_report"):
        # Anche il testo di riserva deve dire subito che non c'e' una seduta
        # nuova: e' quello che leggono Google e l'anteprima di LinkedIn, e una
        # card che promettesse "the August 14 session" per la terza volta di
        # fila sarebbe il difetto visibile proprio dove fa piu' danno.
        w = ed["weekend_report"]
        paragraphs = (w.get("paragraphs") or {}).get("en") or []
        edition_date = ed.get("edition_date_en") or ed.get("edition_date_it")
        session_date = w.get("covers_date_en") or w.get("covers_date_it")
        headline = ed.get("headline_en") or ed.get("headline")
        edition_label, session_label = "Edition of", "news from"
    elif by_index and by_index.get("sp500"):
        paragraphs = (by_index["sp500"].get("paragraphs") or {}).get("en") or []
        edition_date = ed.get("edition_date_en") or ed.get("edition_date_it")
        session_date = ed.get("session_date_en") or ed.get("session_date_it")
        headline = ed.get("headline_en") or ed.get("headline")
        edition_label, session_label = "Edition of", "session of"
    else:
        paragraphs = (ed.get("auto_report") or {}).get("paragraphs") or []
        edition_date = ed.get("edition_date_it")
        session_date = ed.get("session_date_it")
        headline = ed.get("headline")
        edition_label, session_label = "Edizione del", "seduta del"

    first = e(paragraphs[0]) if paragraphs else ""
    return (
        f'<div class="eyebrow">{edition_label} {e(str(edition_date or ""))}'
        f' <span class="dim">&middot; {session_label} {e(str(session_date or ""))}</span></div>\n'
        f'    <h2 class="edition-headline">{e(str(headline or ""))}</h2>\n'
        f'    <div class="edition-text"><p>{first}</p></div>'
    )


def read_template(name: str) -> str:
    path = os.path.join(TEMPLATES_DIR, name)
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        raise TemplateError(
            f"manca il file {path}\n"
            f"  I tre template (page.html, style.css, app.js) devono stare nella\n"
            f"  cartella templates/ accanto a build_public_page.py."
        )


def check_js_syntax(js: str) -> None:
    """Errori di SINTASSI in app.js, con osascript (gia' presente su macOS).

    Non verifica la logica: un campo inesistente passa il controllo e va in errore
    nel browser (dove pero' c'e' il testo di riserva). Sul runner Linux osascript
    non esiste e il controllo si salta: la porta e' il Mac, che sincronizza solo
    dopo un build riuscito.
    """
    if not shutil.which("osascript"):
        return
    tmp = os.path.join(TEMPLATES_DIR, ".controllo_sintassi.js")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(js)
        r = subprocess.run(
            ["osascript", "-l", "JavaScript", tmp],
            capture_output=True, text=True, timeout=30,
        )
        # "script error: ... SyntaxError" = file rotto.
        # "execution error: ... ReferenceError: Can't find variable: document" =
        # file sano, semplicemente non c'e' un browser attorno.
        if "script error" in r.stderr and "SyntaxError" in r.stderr:
            msg = r.stderr.strip().split("\n")[0]
            raise TemplateError(
                f"errore di sintassi in templates/app.js\n  {msg}\n"
                f"  La pagina non viene generata. Correggi e riprova."
            )
    except subprocess.TimeoutExpired:
        pass  # controllo non conclusivo: non e' motivo per fermare il build
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def check_templates(page: str, js: str) -> None:
    """Controlli che fermano il build PRIMA di scrivere index.html."""
    for ph in PLACEHOLDERS:
        n = page.count(ph)
        if n != 1:
            raise TemplateError(
                f"in templates/page.html il segnaposto {ph} compare {n} volte, "
                f"deve comparire esattamente una volta.\n"
                f"  Se l'hai cancellato per sbaglio, rimettilo dov'era."
            )
    if 'id="editionsContent"' not in page:
        raise TemplateError(
            'in templates/page.html manca id="editionsContent".\n'
            "  E' il contenitore dentro cui app.js disegna l'edizione: senza,\n"
            "  la pagina resta vuota. Non rinominarlo."
        )
    for ph in PLACEHOLDERS:
        if ph in js:
            raise TemplateError(
                f"templates/app.js contiene il segnaposto {ph}, che va solo in "
                f"page.html.\n  app.js deve restare JavaScript valido."
            )
    check_js_syntax(js)


def build(editions: list[dict]) -> str:
    page = read_template("page.html")
    css = read_template("style.css")
    js = read_template("app.js")
    check_templates(page, js)

    # "<" scritto <: un titolo di giornale che contenesse "</script" chiuderebbe
    # il tag in anticipo e spegnerebbe la pagina.
    data = json.dumps(slim_editions(editions), ensure_ascii=False).replace("<", "\\u003c")
    # Stesso trattamento dei dati delle edizioni: "<" va neutralizzato perche'
    # una sequenza "</script>" dentro un nome chiuderebbe il blocco JS.
    streaks_json = json.dumps(load_streaks(), ensure_ascii=False).replace("<", "\\u003c")
    shots_json = json.dumps(list_shots(), ensure_ascii=False).replace("<", "\\u003c")

    # I dati per ultimi: se un titolo di giornale contenesse "__APP_JS__" non
    # verrebbe interpretato come segnaposto.
    return (
        page.replace("__STYLE_CSS__", css)
            .replace("__APP_JS__", js)
            .replace("__FALLBACK_HTML__", fallback_html(editions))
            .replace("__EDITIONS_JSON__", data)
            .replace("__STREAKS_JSON__", streaks_json)
            .replace("__SHOTS_JSON__", shots_json)
    )


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    solo_controllo = "--controlla" in sys.argv

    editions = load_editions()
    try:
        html_out = build(editions)
    except TemplateError as e:
        print(f"ERRORE nei template: {e}", file=sys.stderr)
        sys.exit(1)

    if solo_controllo:
        print(f"Template a posto ({len(editions)} edizioni, pagina di {len(html_out) / 1024:.0f} KB).")
        return

    out_dir = args[0] if args else DEFAULT_OUT_DIR
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "index.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_out)

    print(
        f"Pagina pubblica generata: {out_path} "
        f"({os.path.getsize(out_path) / 1024:.0f} KB, {len(editions)} edizioni)"
    )

    write_share_page(out_dir, editions)


# La pagina "post pronto" (vedi share_page.py) va scritta dentro editions/ e non
# nella radice: il workflow notturno committa solo "index.html" e "editions", e
# tenerla qui evita di dover modificare daily.yml — cosa che richiederebbe uno
# scope OAuth che le credenziali locali non hanno, quindi un copia-incolla a mano
# dall'editor web di GitHub a ogni ritocco.
SHARE_PAGE_PATH = os.path.join("editions", "share.html")


def write_share_page(out_dir: str, editions: list[dict]) -> None:
    """Scrive la pagina da cui si pubblica dal telefono. Mai fatale.

    Se qualcosa va storto qui, il sito e' gia' stato scritto e deve restare
    pubblicabile: la pagina di condivisione e' una comodita' in piu', non una
    dipendenza. Si segnala l'errore su stderr e si continua.
    """
    if not editions:
        return
    try:
        import share_page

        path = os.path.join(out_dir, SHARE_PAGE_PATH)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # Tutta la lista: share_page tiene gli ultimi SHARE_DAYS giorni, cosi' un
        # post dimenticato ieri resta raggiungibile dal menu a tendina.
        with open(path, "w", encoding="utf-8") as f:
            f.write(share_page.build(editions))
        n = min(len(editions), share_page.SHARE_DAYS)
        print(f"Pagina 'post pronto' generata: {path} ({n} giorni)")
    except Exception as e:
        print(
            f"ATTENZIONE: pagina 'post pronto' non generata ({type(e).__name__}: {e}).",
            file=sys.stderr,
        )
        print("Il sito e' comunque a posto.", file=sys.stderr)


if __name__ == "__main__":
    main()
