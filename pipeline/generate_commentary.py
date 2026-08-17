"""
Scrive market_summary.json chiamando l'API Claude, cosi' il commento discorsivo
(vedi README, "Il commento discorsivo") non richiede piu' di chiedere a Claude
Code ogni sera: lo scrive da solo, ogni notte, nel job di GitHub Actions — in
inglese e in italiano, con UNA sola chiamata.

DUE MESTIERI, uno per tipo di edizione (vedi build_edition.py):
  - edizione con seduta nuova -> commento della seduta, in market_summary.json;
  - edizione di riassunto (domenica, lunedi', dopo una festivita') -> riassunto
    del fine settimana e "cosa guardare all'apertura", in weekend_summary.json.
Il secondo file e' indicizzato per DATA DELL'EDIZIONE e non per seduta: domenica
e lunedi' condividono la stessa seduta di riferimento, quindi una chiave sulla
seduta farebbe ricomparire di lunedi' il testo di domenica — cioe' la
ripetizione che tutto questo lavoro serve a togliere.

Lo script si sceglie il mestiere da solo leggendo "edition_kind": il workflow di
GitHub continua a chiamarlo con lo stesso identico comando di prima.

Il punto delicato: e' testo generato da un modello che finisce sul sito pubblico
SENZA revisione umana, ogni notte. Per questo il modello scrive SOLO la prosa —
non riceve mai e non puo' mai restituire un link, una testata o un URL: quelli
restano sempre e solo quelli gia' verificati deterministicamente da
mover_reason.py (lo stesso modulo che filtra le fonti per il post LinkedIn).
Se per un titolo non risulta un catalizzatore, il modello viene istruito a
dichiararlo esplicitamente — mai a inventarne uno.

Il commento discute il quadro COMBINATO (i tre indici insieme, vedi
build_edition.py): il materiale include anche le statistiche di ampiezza per
singolo indice (S&P 500/Dow/Nasdaq-100), cosi' il modello puo' notare onestamente
una divergenza tra indici restando ancorato a numeri gia' calcolati, non
inventati.

Se manca la API key, se la chiamata fallisce, o se la risposta non rispetta la
forma attesa (l'insieme dei simboli non coincide esattamente), lo script si
ferma SENZA scrivere nulla ed esce con codice 0: il resto della pipeline
continua con il solo resoconto automatico, come se questo script non esistesse.
La sua assenza non lascia mai la pagina vuota (vedi README, "Limiti noti").

Uso:
    python3 generate_commentary.py           # edizione di oggi
    python3 generate_commentary.py 2026-08-06   # edizione specifica (debug)

Richiede la variabile d'ambiente ANTHROPIC_API_KEY.
"""
import html
import json
import os
import sys

EDITIONS_DIR = "editions"
GENERAL_NEWS_FILE = "general_news_pool.json"
OUT_FILE = "market_summary.json"
WEEKEND_OUT_FILE = "weekend_summary.json"
# Prosa della riga laterale "Top Mercati" (EN+IT). Indicizzata per data
# dell'edizione: le notizie di sabato non sono quelle di domenica. Se manca,
# build_edition.py ricade sulla lista dei titoli top.
MARKETS_BRIEF_OUT_FILE = "markets_brief.json"
MODEL = os.environ.get("COMMENTARY_MODEL", "claude-haiku-4-5-20251001")
MAX_MACRO_HEADLINES = 20

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mover_reason import is_trusted  # noqa: E402


def load_edition(date: str | None):
    if date:
        path = os.path.join(EDITIONS_DIR, f"{date}.json")
    else:
        import glob
        candidates = sorted(glob.glob(os.path.join(EDITIONS_DIR, "*.json")))
        if not candidates:
            raise SystemExit("nessuna edizione trovata: lancia prima build_edition.py")
        path = candidates[-1]
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_macro_headlines() -> list[dict]:
    """Notizie macro/mercato di fonte affidabile, per il contesto discorsivo.

    Solo title+source: niente link nel materiale dato al modello, cosi' non ha
    nulla da poter restituire come fosse un URL verificato.
    """
    try:
        with open(GENERAL_NEWS_FILE, encoding="utf-8") as f:
            pool = json.load(f).get("pool", [])
    except FileNotFoundError:
        return []
    out, seen = [], set()
    for it in pool:
        if it.get("category") != "market":
            continue
        if not is_trusted(it.get("source", "")):
            continue
        t = it.get("title", "")
        if not t or t in seen:
            continue
        seen.add(t)
        out.append({"title": t, "source": it.get("source", "")})
        if len(out) >= MAX_MACRO_HEADLINES:
            break
    return out


def mover_material(m: dict) -> dict:
    r = m.get("reason")
    return {
        "symbol": m["symbol"],
        "name": m["name"],
        "pct_change": m["pct_change"],
        "indices": m.get("indices") or [],
        "reason": {"title": r["title"], "source": r["source"]} if r else None,
    }


def index_breadth(auto_report_by_index: dict) -> dict:
    """Solo i numeri di ampiezza per indice (mai i mover): il materiale che
    permette al modello di notare una divergenza tra indici — es. "il Nasdaq ha
    sovraperformato" — restando ancorato a cifre gia' calcolate."""
    out = {}
    for key in ("sp500", "dow", "nasdaq100"):
        block = auto_report_by_index.get(key)
        if not block:
            continue
        s = block["stats"]
        out[key] = {"n_up": s["n_up"], "n_down": s["n_down"], "avg_pct": s["avg_pct"]}
    return out


TOOL_SCHEMA = {
    "name": "scrivi_commento",
    "description": "Scrive il commento discorsivo della seduta, in inglese e in italiano.",
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["paragraphs_en", "paragraphs_it"],
        "properties": {
            "paragraphs_en": {
                "type": "array",
                "minItems": 2,
                "maxItems": 6,
                "items": {"type": "string", "minLength": 20},
            },
            "paragraphs_it": {
                "type": "array",
                "minItems": 2,
                "maxItems": 6,
                "items": {"type": "string", "minLength": 20},
            },
        },
    },
}

SYSTEM_PROMPT = """You are a financial editor writing the discursive commentary for a US markets \
newsletter, published with no human review. For that reason there is one absolute rule: you may \
write ONLY facts present in the material you are given. You may never:
- cite an outlet, URL, or source that was not given to you;
- attribute a cause to a mover's move if its "reason" field is null — in that case state plainly \
that the tracked outlets report no specific company catalyst for that session, never invent one;
- use HTML markup, markdown, bullet lists, or links: prose paragraphs only.

Write 2-4 paragraphs: first the session's macro context (only from "macro_headlines", citing the \
outlet when it adds credibility), then one paragraph on the gainers and one on the losers, naming \
each mover given in "gainers"/"losers" with its percentage move and, when present, the news that \
explains it. You are given breadth numbers per index (S&P 500, Dow Jones, Nasdaq-100) in \
"index_breadth": you may note a genuine divergence between them (e.g. "the Nasdaq-100 outperformed"), \
but only using those numbers, never invented ones. Analytical, direct tone, like a real financial \
newsletter — not enthusiastic, not alarmist.

You must produce the SAME commentary in two languages: "paragraphs_en" in English (the primary \
version) and "paragraphs_it" in Italian (a faithful equivalent, not a decoration — same facts, same \
structure, same number of paragraphs). Company/outlet names stay as given in both languages. Do not \
translate numbers incorrectly: every percentage and count must match between the two versions."""


WEEKEND_SYSTEM_PROMPT = """You are a financial editor writing the weekend edition of a US markets \
newsletter, published with no human review. The exchanges were CLOSED on the day this edition covers, \
so there is no trading session to report.

The single most important rule of this edition: you must NOT restate the previous session's numbers. \
No breadth counts, no index averages, no top gainers or losers, no company percentage moves from the \
last session. Readers have already received all of that in the previous edition, and repeating it \
across three days is exactly the failure this format exists to fix. You are given no such numbers, so \
any you wrote would be invented.

The other absolute rules, as always: write ONLY facts present in the material you are given; never \
cite an outlet, URL or source that was not given to you; never predict a price or recommend an action; \
no HTML, markdown, bullet lists or links — prose paragraphs only.

Write 3-6 paragraphs, in this order:
1. what actually happened over the closed days, built from "headlines" — group the stories by theme \
rather than listing them, and name the outlet when it adds credibility;
2. one paragraph on the markets that DO trade while the exchanges are shut, using only the figures in \
"weekend_signals" (crypto, index futures, commodities, currencies, each measured from the last US \
close). Describe them as quotes, never as forecasts. If every move is small, say so plainly;
3. only if "niche_signals" is non-empty, one paragraph naming up to 2 of the companies listed there — \
these are companies named in this weekend's news coverage outside the regular market-news cycle, each \
with a "score" measuring how intensely the outlets themselves wrote about the story (strong words, a \
percentage mentioned in the text), NOT a price move and NOT a forecast. Cite the exact headline and \
outlet given, state the score as what it is (a coverage-intensity score, out of 10), and explicitly say \
this is not a prediction of Monday's move. Never invent or state a percentage price change for these \
companies — "score" is the only number "niche_signals" gives you, and it is not a price;
4. a closing paragraph on what the coming session brings, built ONLY from "watchlist" — these are \
scheduled events and outlet previews, not your predictions. Frame them as things to watch, never as \
directional calls.

Analytical, direct tone, like a real financial newsletter — not enthusiastic, not alarmist, and never \
advisory.

You must produce the SAME commentary in two languages: "paragraphs_en" in English (the primary \
version) and "paragraphs_it" in Italian (a faithful equivalent, not a decoration — same facts, same \
structure, same number of paragraphs). Company/outlet names stay as given in both languages. Every \
percentage must match between the two versions."""


def call_model(material: dict, system: str = SYSTEM_PROMPT) -> dict:
    import anthropic

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=MODEL,
        max_tokens=3000,
        temperature=0.4,
        system=system,
        tools=[TOOL_SCHEMA],
        tool_choice={"type": "tool", "name": "scrivi_commento"},
        messages=[{"role": "user", "content": json.dumps(material, ensure_ascii=False)}],
    )
    for block in resp.content:
        if block.type == "tool_use" and block.name == "scrivi_commento":
            return {"en": block.input["paragraphs_en"], "it": block.input["paragraphs_it"]}
    raise RuntimeError("il modello non ha chiamato lo strumento richiesto")


def validate_paragraphs(paragraphs, expected_names: set, lang: str) -> None:
    if not isinstance(paragraphs, list) or not (2 <= len(paragraphs) <= 6):
        raise ValueError(f"[{lang}] numero di paragrafi inatteso: {len(paragraphs) if isinstance(paragraphs, list) else type(paragraphs)}")
    for p in paragraphs:
        if not isinstance(p, str) or len(p.strip()) < 20:
            raise ValueError(f"[{lang}] paragrafo vuoto o troppo corto")
    joined = " ".join(paragraphs).lower()
    missing = [n for n in expected_names if n.split()[0].lower() not in joined]
    if missing:
        print(f"  ATTENZIONE (non bloccante, {lang}): societa' non citate nel testo: {', '.join(missing)}", file=sys.stderr)


def to_html(paragraphs) -> str:
    return "".join(f"<p>{html.escape(p.strip())}</p>" for p in paragraphs)


MAX_DIGEST_HEADLINES = 24


def weekend_material(edition: dict) -> dict:
    """Materiale per il riassunto del fine settimana.

    Contiene di proposito ZERO statistiche della seduta precedente: niente
    ampiezza, niente medie, niente mover. E' la stessa difesa architetturale del
    resto del file — il modello non puo' ripetere numeri che non ha — applicata
    al difetto specifico che questa edizione elimina. Le uniche percentuali che
    riceve sono quelle degli strumenti che hanno DAVVERO scambiato nel fine
    settimana, calcolate da fetch_weekend_signals.py.
    """
    w = edition["weekend_report"]
    headlines = [
        {"title": i["title"], "source": i["source"], "theme": s["label"]["en"]}
        for s in w.get("sections", [])
        for i in s.get("items", [])
    ][:MAX_DIGEST_HEADLINES]

    signals = [
        {
            "instrument": inst["name_en"],
            "group": inst["group"],
            "pct_change_since_last_us_close": inst["pct_change"],
        }
        for group in (w.get("signals") or {}).get("groups", [])
        for inst in group["instruments"]
    ]

    # "score" e' l'unico numero che passa: niente "move_pct_mentioned" (una
    # percentuale trovata nel testo di un titolo, non un prezzo verificato) —
    # darla al modello insieme a un ticker rischierebbe di farla leggere come
    # un movimento di mercato reale, che non e'.
    niche = [
        {"symbol": n["symbol"], "name": n["name"], "score": n["score"],
         "headline": n["title"], "source": n["source"]}
        for n in (w.get("niche_signals") or [])
    ]

    return {
        "covers_date_en": w["covers_date_en"],
        "exchanges_closed": True,
        "last_session_already_published_on": edition["session_date_en"],
        "n_stories_in_window": w["n_items"],
        "n_outlets": w["n_sources"],
        "headlines": headlines,
        "weekend_signals": signals,
        "niche_signals": niche,
        "watchlist": w.get("watchlist", []),
        "macro_headlines": load_macro_headlines(),
    }


def write_weekend_summary(edition: dict) -> None:
    material = weekend_material(edition)
    if not material["headlines"] and not material["weekend_signals"]:
        print("Nessuna notizia e nessun segnale nel fine settimana: niente da commentare.")
        return

    result = call_model(material, system=WEEKEND_SYSTEM_PROMPT)
    for lang in ("en", "it"):
        validate_paragraphs(result[lang], set(), lang)

    out = {
        # Chiave sull'EDIZIONE, non sulla seduta: vedi l'intestazione del file.
        "edition_date": edition["edition_date"],
        "covers_date": edition["weekend_report"]["covers_date"],
        "summary_html_en": to_html(result["en"]),
        "summary_html_it": to_html(result["it"]),
    }
    with open(WEEKEND_OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(
        f"Riassunto del fine settimana scritto in {WEEKEND_OUT_FILE} "
        f"({len(result['en'])} paragrafi EN, {len(result['it'])} paragrafi IT, "
        f"edizione {edition['edition_date']}, notizie del {out['covers_date']})."
    )


# ====== Riga laterale "Top Mercati" ======================================
# Un riassunto BREVE (1-2 paragrafi) delle notizie top della sezione Mercati del
# giorno. Stesse regole ferree del resto del file: solo fatti presenti nel
# materiale, mai una testata o un dato non forniti, nessuna previsione. Il modello
# riceve SOLO titolo+testata dei pochi articoli gia' scelti da build_edition.py.
MARKETS_BRIEF_TOOL = {
    "name": "scrivi_top_mercati",
    "description": "Restituisce un riassunto brevissimo delle notizie top di mercato, in EN e IT.",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary_en": {"type": "string", "description": "1-2 short paragraphs, plain prose."},
            "summary_it": {"type": "string", "description": "La stessa sintesi in italiano."},
        },
        "required": ["summary_en", "summary_it"],
    },
}

MARKETS_BRIEF_SYSTEM_PROMPT = """You write the "Top in Markets" blurb for a daily US-markets newsletter: a very short \
digest of the day's most important markets/macro news.

You are given ONLY a short list of headlines, each with its outlet. Write 1 to 2 tight paragraphs that \
tie the top stories together into what a reader should take away — grouped by theme, not listed one by one.

Absolute rules: use ONLY facts present in the headlines you are given; never cite an outlet or a story \
that was not given; never invent a number, a price or a percentage; never predict a price or recommend \
an action; no HTML, markdown, bullet points or links — plain prose only. Analytical, direct tone.

Produce the SAME blurb in two languages: "summary_en" (primary) and "summary_it" (a faithful Italian \
equivalent — same facts, same length). Outlet names stay as given in both."""


def write_markets_brief(edition: dict) -> None:
    """Prosa breve della riga 'Top Mercati'. Mai fatale: se salta, resta la lista.

    Le notizie le ha gia' scelte build_edition.py (edition["markets_brief"]["items"]),
    identiche a quelle che finiscono nel blocco: cosi' il testo non puo' citare un
    articolo che nella pagina non c'e'.
    """
    items = ((edition.get("markets_brief") or {}).get("items")) or []
    if not items:
        print("Nessuna notizia 'Mercati' per il riassunto laterale: salto (resta la lista).")
        return
    material = {
        "top_markets_headlines": [{"title": i.get("title", ""), "source": i.get("source", "")} for i in items],
    }
    import anthropic

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=MODEL,
        max_tokens=900,
        temperature=0.4,
        system=MARKETS_BRIEF_SYSTEM_PROMPT,
        tools=[MARKETS_BRIEF_TOOL],
        tool_choice={"type": "tool", "name": "scrivi_top_mercati"},
        messages=[{"role": "user", "content": json.dumps(material, ensure_ascii=False)}],
    )
    result = None
    for block in resp.content:
        if block.type == "tool_use" and block.name == "scrivi_top_mercati":
            result = block.input
            break
    if not result or not result.get("summary_en") or not result.get("summary_it"):
        raise RuntimeError("il modello non ha restituito il riassunto 'Top Mercati'")

    out = {
        "edition_date": edition["edition_date"],
        "prose_html_en": to_html([result["summary_en"].strip()]),
        "prose_html_it": to_html([result["summary_it"].strip()]),
    }
    with open(MARKETS_BRIEF_OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"Riga 'Top Mercati' scritta in {MARKETS_BRIEF_OUT_FILE} (edizione {edition['edition_date']}, {len(items)} notizie).")


def main():
    date_arg = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else None

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY non impostata: salto il commento automatico (nessun errore).")
        return

    try:
        edition = load_edition(date_arg)

        # Riga laterale "Top Mercati": vale per OGNI edizione (feriale o weekend).
        # In un try a se': se la sua chiamata fallisce, il commento principale qui
        # sotto deve comunque essere tentato, e viceversa.
        try:
            write_markets_brief(edition)
        except Exception as e:
            print(f"ATTENZIONE: riga 'Top Mercati' non generata ({type(e).__name__}: {e}).", file=sys.stderr)

        # Il bivio. Un'edizione di riassunto non ha mover da spiegare: chiederne
        # il commento di seduta produrrebbe proprio il testo che non deve uscire.
        if edition.get("edition_kind") == "weekend_recap" and edition.get("weekend_report"):
            write_weekend_summary(edition)
            return

        combined = edition["auto_report_by_index"]["combined"]
        gainers = [mover_material(m) for m in combined["gainers"]]
        losers = [mover_material(m) for m in combined["losers"]]
        material = {
            "session_date_en": edition["session_date_en"],
            "stats": combined["stats"],
            "index_breadth": index_breadth(edition["auto_report_by_index"]),
            "gainers": gainers,
            "losers": losers,
            "macro_headlines": load_macro_headlines(),
        }

        result = call_model(material)
        expected_names = {m["name"] for m in gainers + losers}
        validate_paragraphs(result["en"], expected_names, "en")
        validate_paragraphs(result["it"], expected_names, "it")

        out = {
            "date": edition["session_date"],
            "summary_html_en": to_html(result["en"]),
            "summary_html_it": to_html(result["it"]),
        }
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(
            f"Commento discorsivo scritto in {OUT_FILE} "
            f"({len(result['en'])} paragrafi EN, {len(result['it'])} paragrafi IT, seduta {edition['session_date']})."
        )

    except Exception as e:
        print(f"ATTENZIONE: commento automatico non generato ({type(e).__name__}: {e}).", file=sys.stderr)
        print("Nessun problema: l'edizione uscira' con il solo resoconto automatico.", file=sys.stderr)
        return


if __name__ == "__main__":
    main()
