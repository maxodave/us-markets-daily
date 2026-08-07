"""
Scrive market_summary.json chiamando l'API Claude, cosi' il commento discorsivo
(vedi README, "Il commento discorsivo") non richiede piu' di chiedere a Claude
Code ogni sera: lo scrive da solo, ogni notte, nel job di GitHub Actions — in
inglese e in italiano, con UNA sola chiamata.

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


def call_model(material: dict) -> dict:
    import anthropic

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=MODEL,
        max_tokens=3000,
        temperature=0.4,
        system=SYSTEM_PROMPT,
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


def main():
    date_arg = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else None

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY non impostata: salto il commento automatico (nessun errore).")
        return

    try:
        edition = load_edition(date_arg)
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

        def to_html(paragraphs):
            return "".join(f"<p>{html.escape(p.strip())}</p>" for p in paragraphs)

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
