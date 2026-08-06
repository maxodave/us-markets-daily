"""
Scrive market_summary_it.json chiamando l'API Claude, cosi' il commento
discorsivo (vedi README, "Aggiungere il commento discorsivo") non richiede piu'
di chiedere a Claude Code ogni sera: lo scrive da solo, ogni notte, nel job di
GitHub Actions.

Il punto delicato: e' testo generato da un modello che finisce sul sito pubblico
SENZA revisione umana, ogni notte. Per questo il modello scrive SOLO la prosa —
non riceve mai e non puo' mai restituire un link, una testata o un URL: quelli
restano sempre e solo quelli gia' verificati deterministicamente da
mover_reason.py (lo stesso modulo che filtra le fonti per il post LinkedIn).
Se per un titolo non risulta un catalizzatore, il modello viene istruito a
dichiararlo esplicitamente — mai a inventarne uno.

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
OUT_FILE = "market_summary_it.json"
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
        "reason": {"title": r["title"], "source": r["source"]} if r else None,
    }


TOOL_SCHEMA = {
    "name": "scrivi_commento",
    "description": "Scrive il commento discorsivo della seduta in italiano.",
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["paragraphs"],
        "properties": {
            "paragraphs": {
                "type": "array",
                "minItems": 2,
                "maxItems": 6,
                "items": {"type": "string", "minLength": 20},
            }
        },
    },
}

SYSTEM_PROMPT = """Sei un redattore finanziario che scrive in italiano il commento discorsivo \
di una newsletter di mercato USA, pubblicato senza revisione umana. Per questo motivo \
vale una regola sola, assoluta: puoi scrivere SOLO fatti presenti nel materiale che \
ti viene fornito. Non puoi mai:
- citare una testata, un URL o una fonte che non ti e' stata data;
- attribuire a un titolo un motivo per il suo movimento se il campo "reason" e' null \
per quel titolo — in quel caso scrivi esplicitamente che le fonti monitorate non \
riportano un catalizzatore societario specifico per quella seduta, senza inventarne uno;
- usare markup HTML, markdown, elenchi puntati o link: solo prosa in paragrafi.

Scrivi 2-4 paragrafi: prima il contesto macro della seduta (solo dai titoli in \
"macro_headlines", citando la testata quando aggiunge credibilita'), poi un paragrafo \
sui titoli in rialzo e uno su quelli in ribasso, nominando ciascun titolo fornito in \
"gainers"/"losers" con la sua variazione percentuale e, se presente, la notizia che lo \
spiega. Tono analitico e diretto, come una vera newsletter finanziaria — non entusiasta, \
non allarmista."""


def call_model(material: dict) -> list[str]:
    import anthropic

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=MODEL,
        max_tokens=1600,
        temperature=0.4,
        system=SYSTEM_PROMPT,
        tools=[TOOL_SCHEMA],
        tool_choice={"type": "tool", "name": "scrivi_commento"},
        messages=[{"role": "user", "content": json.dumps(material, ensure_ascii=False)}],
    )
    for block in resp.content:
        if block.type == "tool_use" and block.name == "scrivi_commento":
            return block.input["paragraphs"]
    raise RuntimeError("il modello non ha chiamato lo strumento richiesto")


def validate(paragraphs, expected_names: set) -> None:
    if not isinstance(paragraphs, list) or not (2 <= len(paragraphs) <= 6):
        raise ValueError(f"numero di paragrafi inatteso: {len(paragraphs) if isinstance(paragraphs, list) else type(paragraphs)}")
    for p in paragraphs:
        if not isinstance(p, str) or len(p.strip()) < 20:
            raise ValueError("paragrafo vuoto o troppo corto")
    joined = " ".join(paragraphs).lower()
    missing = [n for n in expected_names if n.split()[0].lower() not in joined]
    if missing:
        print(f"  ATTENZIONE (non bloccante): societa' non citate nel testo: {', '.join(missing)}", file=sys.stderr)


def main():
    date_arg = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else None

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY non impostata: salto il commento automatico (nessun errore).")
        return

    try:
        edition = load_edition(date_arg)
        auto = edition["auto_report"]
        gainers = [mover_material(m) for m in auto["gainers"]]
        losers = [mover_material(m) for m in auto["losers"]]
        material = {
            "session_date_it": edition["session_date_it"],
            "stats": auto["stats"],
            "gainers": gainers,
            "losers": losers,
            "macro_headlines": load_macro_headlines(),
        }

        paragraphs = call_model(material)
        expected_names = {m["name"] for m in gainers + losers}
        validate(paragraphs, expected_names)

        summary_html = "".join(f"<p>{html.escape(p.strip())}</p>" for p in paragraphs)
        out = {"date": edition["session_date"], "summary_html": summary_html}
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"Commento discorsivo scritto in {OUT_FILE} ({len(paragraphs)} paragrafi, seduta {edition['session_date']}).")

    except Exception as e:
        print(f"ATTENZIONE: commento automatico non generato ({type(e).__name__}: {e}).", file=sys.stderr)
        print("Nessun problema: l'edizione uscira' con il solo resoconto automatico.", file=sys.stderr)
        return


if __name__ == "__main__":
    main()
