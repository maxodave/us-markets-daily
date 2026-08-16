"""
Genera la pagina "post pronto da condividere", quella che si apre DAL TELEFONO
la mattina per pubblicare su Substack senza toccare il Mac.

Perche' esiste: il job notturno produceva `publish/*-substack.html`, un file
locale sul Mac. Dal telefono, in viaggio, e' irraggiungibile. Questa pagina
viene invece pubblicata da GitHub insieme al sito, quindi e' un indirizzo web
che si apre da qualsiasi dispositivo.

Il flusso, tre tap: Copia titolo -> Copia sottotitolo -> Copia corpo, poi
"Apri Substack" e Pubblica.

Contiene gli ultimi SHARE_DAYS giorni, scegliibili da un menu a tendina: se una
sera ci si dimentica di pubblicare, il post di quel giorno e' ancora li'.
Perche' una finestra e non tutto l'archivio: non e' una questione di costo (la
pagina e' solo testo assemblato, nessuna chiamata a un modello, e il file viene
riscritto ogni notte invece che accresciuto) ma di uso — dopo un anno un menu da
365 voci sarebbe inutilizzabile e la pagina peserebbe oltre un megabyte.

Sul contenuto pubblico: quanto c'e' qui e' lo stesso testo che il sito mostra
gia' pubblicamente a mezzanotte (stesse statistiche, stessi mover, stesse
notizie). Non anticipa nulla che non sia gia' online — e' solo lo stesso
materiale impaginato per essere copiato.

Non e' uno script da lanciare a mano: lo chiama build_public_page.py, che gira
nel job notturno su GitHub. Vedi README, "Routine giornaliera".
"""
import html
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# Quanti giorni tenere nel menu. E' l'unico numero da cambiare per allargare la
# finestra: il resto della pagina si adatta da solo.
SHARE_DAYS = 7

# L'editor di un nuovo post. Aprendolo si crea una bozza vuota, pronta a
# ricevere i tre incolla.
SUBSTACK_NEW_POST = "https://maximedaverio.substack.com/publish/post?type=newsletter"

TEMPLATE = """<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<title>Post pronto — __LATEST_DATE__</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<style>
  :root {
    --bg:#0b0d12; --panel:#12151c; --border:#262b36; --text:#e8eaed;
    --muted:#8a90a0; --accent:#5b8def; --ok:#22c55e;
  }
  @media (prefers-color-scheme: light) {
    :root { --bg:#f5f6f8; --panel:#fff; --border:#e0e2e8; --text:#0a0934; --muted:#6b7280; }
  }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--text); overflow-wrap:break-word;
         font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif; }
  .wrap { max-width:720px; margin:0 auto; padding:20px 16px 60px; }
  h1 { font-size:1.25rem; margin:0 0 4px; }
  .sub { color:var(--muted); font-size:.85rem; margin-bottom:14px; }
  /* Il selettore del giorno: grande quanto un pulsante, perche' si usa col
     pollice. -webkit-appearance:none toglie lo stile di sistema di iOS, che
     altrimenti ignora sfondo e bordo. */
  .daybar { margin-bottom:18px; }
  select { width:100%; padding:14px 16px; font-size:1rem; font-weight:600;
           border-radius:10px; border:1px solid var(--accent);
           background:var(--panel); color:var(--text); -webkit-appearance:none;
           appearance:none; }
  .daybar .hint { margin-top:8px; }
  .step { background:var(--panel); border:1px solid var(--border); border-radius:12px;
          padding:14px 16px; margin-bottom:14px; }
  .step-n { font-size:.7rem; text-transform:uppercase; letter-spacing:.07em;
            color:var(--muted); margin-bottom:8px; }
  .val { font-size:1rem; line-height:1.45; margin-bottom:12px; }
  /* Il corpo e' alto: si limita in altezza con lo scroll interno, altrimenti i
     pulsanti finiscono fuori schermo e il senso della pagina (tre tap) si perde. */
  .body-preview { max-height:220px; overflow-y:auto; font-size:.9rem; line-height:1.5;
                  border:1px solid var(--border); border-radius:8px; padding:12px;
                  margin-bottom:12px; }
  .body-preview ul { padding-left:20px; margin:8px 0; }
  .body-preview li { margin-bottom:6px; }
  .body-preview p { margin:0 0 10px; }
  /* Bersagli grandi: si usa col pollice, spesso in movimento. */
  button, a.btn { display:block; width:100%; padding:14px 16px; font-size:1rem;
                  font-weight:600; border-radius:10px; border:1px solid var(--border);
                  background:var(--panel); color:var(--text); cursor:pointer;
                  text-align:center; text-decoration:none; -webkit-appearance:none; }
  button:active, a.btn:active { opacity:.7; }
  button.done { border-color:var(--ok); color:var(--ok); }
  a.btn.go { background:var(--accent); border-color:var(--accent); color:#fff;
             margin-top:22px; }
  .hint { color:var(--muted); font-size:.8rem; margin-top:10px; line-height:1.45; }
  .day[hidden] { display:none; }
  /* Un giorno diverso da quello di oggi: si segnala, per non pubblicare per
     sbaglio il post di tre giorni fa credendolo quello di stamattina. */
  .old-warning { background:var(--panel); border:1px solid var(--accent);
                 border-radius:10px; padding:12px 14px; margin-bottom:14px;
                 font-size:.85rem; line-height:1.45; }
  details { margin-top:26px; }
  summary { color:var(--muted); font-size:.85rem; cursor:pointer; padding:8px 0; }
  footer { margin-top:30px; padding-top:16px; border-top:1px solid var(--border);
           color:var(--muted); font-size:.75rem; line-height:1.5; }
</style>
</head>
<body>
<div class="wrap">
  <h1>Post pronto da pubblicare</h1>
  <div class="sub">Scegli il giorno, copia, incolla su Substack.</div>

  <div class="daybar">
    <select id="daySelect" aria-label="Scegli l'edizione">
__OPTIONS__
    </select>
    <div class="hint">Ultimi __N_DAYS__ giorni. Se una sera hai saltato la
      pubblicazione, il post di quel giorno e' ancora qui.</div>
  </div>

__DAYS__

  <a class="btn go" href="__SUBSTACK_URL__" target="_blank" rel="noopener">
    Apri Substack e incolla &rarr;
  </a>

  <footer>
    Questa pagina la rigenera GitHub ogni notte insieme al sito: al mattino mostra
    sempre l'edizione del giorno, senza che il Mac sia acceso.
    Nulla viene pubblicato da qui — premere "Pubblica" su Substack resta un tuo gesto.
  </footer>
</div>

<script>
function feedback(btn, msg) {
  const original = btn.dataset.original || btn.textContent;
  btn.dataset.original = original;
  btn.textContent = msg;
  btn.classList.add("done");
  setTimeout(function () {
    btn.textContent = original;
    btn.classList.remove("done");
  }, 2200);
}

async function copyFrom(btn) {
  // Il contenuto si cerca DENTRO il giorno del pulsante, non per id globale:
  // in pagina ci sono piu' giorni con gli stessi campi, e un id ripetuto
  // farebbe copiare sempre il primo.
  const el = btn.closest(".day").querySelector("." + btn.dataset.copy);
  const rich = btn.dataset.rich === "1";
  const text = el.innerText;
  try {
    if (rich && window.ClipboardItem && navigator.clipboard.write) {
      await navigator.clipboard.write([new ClipboardItem({
        "text/html": new Blob([el.innerHTML], { type: "text/html" }),
        "text/plain": new Blob([text], { type: "text/plain" }),
      })]);
    } else {
      await navigator.clipboard.writeText(text);
      if (rich) { feedback(btn, "✓ copiato (senza formattazione)"); return; }
    }
    feedback(btn, "✓ copiato");
  } catch (e) {
    // Ultima spiaggia: si prova il testo semplice, e se anche quello non passa
    // si dice all'utente di selezionare a mano invece di fallire in silenzio.
    try {
      await navigator.clipboard.writeText(text);
      feedback(btn, "✓ copiato (senza formattazione)");
    } catch (e2) {
      feedback(btn, "copia non riuscita — seleziona a mano");
    }
  }
}

document.querySelectorAll("button[data-copy]").forEach(function (btn) {
  btn.addEventListener("click", function () { copyFrom(btn); });
});

const daySelect = document.getElementById("daySelect");
function showDay(date) {
  document.querySelectorAll(".day").forEach(function (d) {
    d.hidden = d.dataset.day !== date;
  });
}
daySelect.addEventListener("change", function () { showDay(daySelect.value); });
showDay(daySelect.value);
</script>
</body>
</html>
"""

DAY_BLOCK = """  <div class="day" data-day="__DATE__">
__WARNING__    <div class="step">
      <div class="step-n">1 — Titolo</div>
      <div class="val f-title">__TITLE__</div>
      <button data-copy="f-title">Copia titolo</button>
    </div>

    <div class="step">
      <div class="step-n">2 — Sottotitolo</div>
      <div class="val f-subtitle">__SUBTITLE__</div>
      <button data-copy="f-subtitle">Copia sottotitolo</button>
    </div>

    <div class="step">
      <div class="step-n">3 — Corpo del post</div>
      <div class="body-preview f-body">__BODY__</div>
      <button data-copy="f-body" data-rich="1">Copia corpo (con formattazione)</button>
      <div class="hint">Incolla nel corpo del post: elenchi, corsivi e il link in
        fondo restano formattati.</div>
    </div>

    <details>
      <summary>Serve anche il post per LinkedIn?</summary>
      <div class="step" style="margin-top:12px">
        <div class="step-n">Testo LinkedIn</div>
        <div class="body-preview f-linkedin" style="white-space:pre-wrap">__LINKEDIN__</div>
        <button data-copy="f-linkedin">Copia testo LinkedIn</button>
        <div class="hint">LinkedIn non interpreta la formattazione: questo si copia
          come testo semplice, com'e'.</div>
      </div>
    </details>
  </div>
"""


def _sections(ed: dict):
    """Titolo, sottotitolo, corpo e testo LinkedIn di una singola edizione."""
    import build_publish as bp

    s = bp.build_sections(ed)

    # render_substack() dichiara la codifica per chi apre il file da solo: qui il
    # <meta> lo mette gia' lo scheletro della pagina, e lasciarlo produrrebbe un
    # tag duplicato dentro il corpo da copiare.
    body = re.sub(r'<meta charset="utf-8">\s*', "", bp.render_substack(s))

    linkedin = bp.render_linkedin(s)
    # Le righe '#' iniziali sono le istruzioni per chi legge il file su disco:
    # in una pagina con un pulsante "copia" non servono, e copiate finirebbero
    # dentro il post.
    lines = linkedin.splitlines()
    i = 0
    while i < len(lines) and lines[i].startswith("#"):
        i += 1
    linkedin = "\n".join(lines[i:]).strip()

    return s["substack_title"], s["substack_subtitle"], body, linkedin


def build(editions: list[dict]) -> str:
    """HTML della pagina, dagli ultimi SHARE_DAYS giorni (il piu' recente primo).

    Importa build_publish dentro _sections e non in cima al modulo:
    build_public_page.py chiama questa funzione dentro un try/except, cosi' se
    build_publish non fosse presente (o cambiasse forma) il sito esce comunque —
    la pagina di condivisione e' un extra, non deve poter far fallire la
    pubblicazione.
    """
    e = html.escape
    recent = editions[:SHARE_DAYS]
    if not recent:
        raise ValueError("nessuna edizione da mostrare")

    options, days = [], []
    for i, ed in enumerate(recent):
        date = str(ed.get("edition_date") or "")
        label_ed = str(ed.get("edition_date_en") or ed.get("edition_date_it") or date)
        label_se = str(ed.get("session_date_en") or ed.get("session_date_it") or "")
        label = f"Edizione del {label_ed}"
        if label_se:
            label += f" · seduta del {label_se}"
        if i == 0:
            label += "  (l'ultima)"

        options.append(
            f'      <option value="{e(date)}">{e(label)}</option>'
        )

        title, subtitle, body, linkedin = _sections(ed)
        warning = ""
        if i > 0:
            warning = (
                f'    <div class="old-warning">Stai guardando l\'edizione del '
                f'<b>{e(label_ed)}</b>, non l\'ultima. Se cercavi quella di oggi, '
                f"scegli la prima voce del menu.</div>\n"
            )
        days.append(
            DAY_BLOCK
            .replace("__DATE__", e(date))
            .replace("__WARNING__", warning)
            .replace("__TITLE__", e(title))
            .replace("__SUBTITLE__", e(subtitle))
            .replace("__LINKEDIN__", e(linkedin))
            # Il corpo per ultimo e come HTML vero (non escapato): e' il contenuto
            # che va copiato con la formattazione. Per ultimo cosi' un titolo di
            # giornale che contenesse "__TITLE__" non venga preso per un segnaposto.
            .replace("__BODY__", body)
        )

    latest = recent[0]
    return (
        TEMPLATE
        .replace("__LATEST_DATE__", e(str(latest.get("edition_date_en") or latest.get("edition_date") or "")))
        .replace("__N_DAYS__", str(len(recent)))
        .replace("__SUBSTACK_URL__", SUBSTACK_NEW_POST)
        .replace("__OPTIONS__", "\n".join(options))
        .replace("__DAYS__", "\n".join(days))
    )
