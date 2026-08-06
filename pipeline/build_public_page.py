"""
Genera la pagina pubblica autonoma (index.html) da pubblicare online — solo la
parte editoriale (edizione del giorno + feed notizie con immagini + archivio),
stesso design della scheda "Riassunto mercati USA" della dashboard privata.

Non include MAI: la tabella dei 503 titoli, il pannello "Segnali di mercato",
ne' alcun dato dei singoli titoli oltre a quello gia' pubblico nelle edizioni.
Le immagini restano in hotlink dai server delle testate (fonte e link sempre
visibili), per scelta esplicita dell'utente — vedi README, sezione "Limiti noti",
per l'avvertenza sulla licenza d'uso.

Uso:
    python3 build_public_page.py [cartella_output]
    (default cartella_output: ~/Sites/us-markets-daily, il repository pubblico
    separato spinto su GitHub Pages — vedi README)
"""
import glob
import json
import os
import re
import sys
from datetime import datetime

EDITIONS_DIR = "editions"
# Percorso del repository pubblico separato (vedi README) — DELIBERATAMENTE fuori
# da Cursor_Projects: un default relativo (es. "../../sito") finirebbe dentro
# questo repo privato, creando un repository git annidato per errore.
DEFAULT_OUT_DIR = os.path.expanduser("~/Sites/us-markets-daily")

MESI_IT = {
    1: "gennaio", 2: "febbraio", 3: "marzo", 4: "aprile", 5: "maggio", 6: "giugno",
    7: "luglio", 8: "agosto", 9: "settembre", 10: "ottobre", 11: "novembre", 12: "dicembre",
}


def italian_date(date_str: str) -> str:
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return f"{d.day} {MESI_IT[d.month]} {d.year}"
    except Exception:
        return date_str or "n/d"


def load_editions() -> list[dict]:
    editions = []
    for p in glob.glob(os.path.join(EDITIONS_DIR, "*.json")):
        try:
            with open(p) as f:
                ed = json.load(f)
        except Exception as e:
            print(f"  ! edizione non leggibile {p}: {e}")
            continue
        if not ed.get("edition_date"):
            continue
        editions.append(ed)
    editions.sort(key=lambda e: e["edition_date"], reverse=True)
    return editions


TEMPLATE = """<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<title>US Markets Daily</title>
<meta name="description" content="Resoconto giornaliero e feed notizie sui mercati USA — solo ricerca/monitoraggio, non consulenza di investimento.">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {
    --bg: #0b0d12; --panel: #12151c; --panel-2: #171b24; --border: #262b36;
    --text: #e8eaed; --muted: #8a90a0; --accent: #5b8def;
    --green-1:#0d3321; --green-2:#14532d; --green-3:#1e7a3d; --green-4:#22c55e; --green-5:#4ade80;
    --red-1:#3a1414; --red-2:#5c1a1a; --red-3:#8a1f1f; --red-4:#ef4444; --red-5:#f87171;
    --cat-mercati:#2f55e8; --cat-italia:#22c55e; --cat-crypto:#f5c542;
    --cat-tech:#ff8e82; --cat-scienza:#a78bfa;
  }
  @media (prefers-color-scheme: light) {
    :root { --bg:#f5f6f8; --panel:#ffffff; --panel-2:#f0f1f4; --border:#e0e2e8; --text:#0a0934; --muted:#6b7280; }
  }
  :root[data-theme="light"] { --bg:#f5f6f8; --panel:#ffffff; --panel-2:#f0f1f4; --border:#e0e2e8; --text:#0a0934; --muted:#6b7280; }
  :root[data-theme="dark"] { --bg:#0b0d12; --panel:#12151c; --panel-2:#171b24; --border:#262b36; --text:#e8eaed; --muted:#8a90a0; }

  * { box-sizing: border-box; }
  /* Rete di sicurezza contro l'overflow orizzontale su mobile: una stringa lunga
     senza spazi (es. un elenco di testate separate da "/") altrimenti allarga
     l'intera pagina e comprime tutto il contenuto a sinistra. break-word spezza
     solo quando la parola non entrerebbe, quindi non danneggia il testo normale. */
  body { margin:0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
         background:var(--bg); color:var(--text); overflow-wrap: break-word; }
  .wrap { max-width: 1400px; margin: 0 auto; padding: 24px 20px 60px; }
  h1 { font-size: 1.5rem; margin: 0 0 4px; }
  .subtitle { color: var(--muted); font-size: 0.9rem; margin-bottom: 16px; }
  .disclaimer { background: var(--panel-2); border: 1px solid var(--border); border-radius: 10px; padding: 12px 16px; font-size: 0.85rem; color: var(--muted); margin-bottom: 20px; }
  .disclaimer b { color: var(--text); }
  .pct { font-weight:700; padding:3px 8px; border-radius:6px; display:inline-block; min-width:64px; text-align:center; }
  .sym { font-weight: 700; }
  .name { color: var(--muted); font-size: 0.82em; }

  .edition { border-top: 2px solid var(--text); padding-top: 18px; margin-bottom: 56px; }
  .eyebrow { font-size: 1.35rem; font-weight: 800; text-transform: uppercase; line-height: 1;
             letter-spacing: -0.005em; font-stretch: condensed; margin-bottom: 14px; }
  .eyebrow .dim { color: var(--muted); font-weight: 700; }
  .edition-headline { font-size: 2.1rem; font-weight: 700; line-height: 1.12; letter-spacing: -0.02em; margin: 0 0 12px; max-width: 22ch; }
  .edition-meta { font-size: 0.74rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); margin-bottom: 24px; }
  .edition-body { display: grid; grid-template-columns: minmax(0, 1.55fr) minmax(0, 1fr); gap: 40px; align-items: start; }
  /* minmax(0, 1fr) e non "1fr": una colonna 1fr nuda ha minimo implicito auto e non
     puo' restringersi sotto la larghezza minima del contenuto (la riga mover usa
     white-space: nowrap), quindi su schermi stretti sfonderebbe il contenitore. */
  @media (max-width: 900px) { .edition-body { grid-template-columns: minmax(0, 1fr); gap: 28px; } .edition-headline { font-size: 1.6rem; max-width: none; } }
  .edition-text p { margin: 0 0 14px; font-size: 1rem; line-height: 1.62; }
  .edition-text p:last-child { margin-bottom: 0; }
  .commentary { border-left: 3px solid var(--accent); padding-left: 18px; margin-top: 22px; }
  .commentary-label { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.07em; color: var(--muted); margin-bottom: 8px; }

  .stat-strip { display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 1px; background: var(--border); border: 1px solid var(--border); margin-bottom: 26px; }
  .stat { background: var(--panel); padding: 14px 16px; }
  .stat .v { font-size: 1.45rem; font-weight: 700; line-height: 1.1; }
  .stat .k { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); margin-top: 4px; }

  .movers-col h4 { font-size: 0.74rem; text-transform: uppercase; letter-spacing: 0.07em; color: var(--muted); margin: 0 0 10px; }
  .mover { padding: 11px 0; border-bottom: 1px solid var(--border); }
  .mover:last-child { border-bottom: none; }
  .mover-head { display: flex; gap: 10px; align-items: baseline; }
  .mover .sym { min-width: 54px; }
  .mover .mname { flex: 1; font-size: 0.86rem; color: var(--muted); min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  /* La notizia che spiega il movimento: e' il pezzo che rende leggibile l'elenco,
     quindi ha lo stesso peso visivo del nome, non quello di una didascalia. */
  .mover-reason { display: block; margin-top: 5px; font-size: 0.84rem; line-height: 1.4;
                  color: var(--text); text-decoration: none; }
  a.mover-reason:hover { text-decoration: underline; }
  .mover-reason.none { color: var(--muted); font-style: italic; }
  .mr-source { font-weight: 700; text-transform: uppercase; font-size: 0.72rem;
               letter-spacing: 0.04em; color: var(--muted); margin-right: 7px; }
  .movers-split { display: grid; grid-template-columns: minmax(0, 1fr); gap: 26px; }

  .section-head { display: flex; align-items: baseline; justify-content: space-between; gap: 16px; flex-wrap: wrap;
                  border-top: 2px solid var(--text); padding-top: 14px; margin: 0 0 18px; }
  .section-head h3 { font-size: 1.35rem; font-weight: 800; text-transform: uppercase; font-stretch: condensed; margin: 0; letter-spacing: -0.005em; }
  .cat-filters { display: flex; gap: 6px; flex-wrap: wrap; }
  .cat-chip { border: 1px solid var(--border); background: var(--panel); padding: 5px 12px; font-size: 0.76rem;
              text-transform: uppercase; letter-spacing: 0.04em; cursor: pointer; color: var(--text); user-select: none; }
  .cat-chip.active { background: var(--text); color: var(--bg); border-color: var(--text); }

  .feed-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(290px, 1fr)); gap: 24px; }
  .feed-card { background: var(--panel); border: 1px solid var(--border); display: flex; flex-direction: column;
               text-decoration: none; color: var(--text); overflow: hidden; transition: border-color .15s ease; }
  .feed-card:hover { border-color: var(--text); }
  .feed-thumb { width: 100%; aspect-ratio: 16 / 10; overflow: hidden; background: var(--panel-2); position: relative; }
  .feed-thumb img { width: 100%; height: 100%; object-fit: cover; display: block; transition: transform .35s ease; }
  .feed-card:hover .feed-thumb img { transform: scale(1.04); }
  .feed-thumb.no-img { display: none; }
  .feed-card-body { padding: 20px; display: flex; flex-direction: column; gap: 9px; flex: 1; }
  .feed-source { font-size: 1.05rem; font-weight: 800; text-transform: uppercase; font-stretch: condensed;
                 line-height: 1.05; display: flex; align-items: center; gap: 8px; }
  .cat-dot { width: 9px; height: 9px; flex: 0 0 auto; }
  .feed-title { font-size: 1.02rem; font-weight: 600; line-height: 1.32; }
  .feed-summary { font-size: 0.86rem; line-height: 1.5; color: var(--muted); }
  .feed-date { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); margin-top: auto; padding-top: 6px; }

  .archive-toggle { background: transparent; border: 1px solid var(--border); color: var(--text); padding: 10px 18px;
                    font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.06em; cursor: pointer; }
  .archive-toggle:hover { border-color: var(--accent); }
  .archive-item { border-top: 1px solid var(--border); padding: 16px 0; }
  .archive-item .a-date { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); }
  .archive-item .a-title { font-size: 1.05rem; font-weight: 600; margin-top: 4px; }
  .no-edition { background: var(--panel-2); border: 1px solid var(--border); padding: 16px; font-size: 0.9rem; color: var(--muted); }
  footer { margin-top: 40px; padding-top: 20px; border-top: 1px solid var(--border); font-size: 0.78rem; color: var(--muted); }
  footer a { color: var(--muted); }

  /* ====== Mobile ======
     La maggior parte dei lettori arriva da un link su LinkedIn, quindi da telefono:
     qui si stringono i margini, si riducono i titoli e la striscia statistiche passa
     a 2 colonne (con l'ultima cella a piena larghezza, cosi' non resta un buco). */
  @media (max-width: 600px) {
    .wrap { padding: 16px 14px 44px; }
    h1 { font-size: 1.3rem; }
    .edition-headline { font-size: 1.45rem; letter-spacing: -0.01em; }
    .eyebrow { font-size: 1.05rem; }
    .section-head h3 { font-size: 1.1rem; }
    .stat-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .stat { padding: 12px 12px; }
    .stat .v { font-size: 1.2rem; }
    .stat:last-child { grid-column: 1 / -1; }
    .feed-grid { grid-template-columns: 1fr; gap: 18px; }
    .feed-card-body { padding: 16px; }
    .edition { margin-bottom: 40px; }
    .mover .sym { min-width: 46px; }
    /* Su mobile il nome societa' va a capo invece di essere troncato con "...":
       su una pagina che si scorre lo spazio verticale non costa, e un nome tagliato
       a meta' ("Alexandria Real Estate Equit...") e' meno utile di due righe. */
    .mover-head { align-items: flex-start; }
    .mover .mname { font-size: 0.8rem; white-space: normal; overflow: visible; text-overflow: clip; line-height: 1.3; }
    .mover-reason { font-size: 0.82rem; }
  }
</style>
</head>
<body>
<div class="wrap">
  <h1>US Markets Daily</h1>
  <div class="subtitle">Resoconto giornaliero dei mercati USA &middot; ultimo aggiornamento <span id="gendate"></span></div>
  <div class="disclaimer">
    <b>Solo ricerca/monitoraggio.</b> Nessun consiglio di investimento, nessuna operazione eseguita.
    Dati di mercato via Yahoo Finance, notizie via feed pubblici delle testate
    (Reuters, Bloomberg, FT, WSJ, CNBC, MarketWatch, Barron's, NYT, Forbes, Yahoo Finance e altre).
    Ogni decisione di acquisto/vendita resta esclusivamente tua.
  </div>

  <div id="editionsContent"></div>

  <footer>
    Le immagini restano di proprieta' delle rispettive testate, linkate alla fonte originale.
  </footer>
</div>

<script>
const EDITIONS = __EDITIONS_JSON__;
const CATEGORIES = [
  { key: "mercati", label: "Mercati" },
  { key: "italia", label: "Italia" },
  { key: "crypto", label: "Crypto" },
  { key: "tech", label: "Tech" },
  { key: "scienza", label: "Scienza" },
];
let feedState = { category: null, showArchive: false };

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]));
}
function fmtPct(v) { return (v > 0 ? "+" : "") + Number(v).toFixed(2).replace(".", ",") + "%"; }

function pctColor(pct) {
  if (pct <= -5) return { bg: "var(--red-3)", fg: "#fff" };
  if (pct < 0) return { bg: "var(--red-1)", fg: "var(--red-5)" };
  if (pct <= 2.5) return { bg: "var(--green-1)", fg: "var(--green-5)" };
  if (pct <= 10) return { bg: "var(--green-2)", fg: "var(--green-5)" };
  if (pct <= 20) return { bg: "var(--green-3)", fg: "#fff" };
  return { bg: "var(--green-4)", fg: "#0b0d12" };
}

function moverRow(m) {
  const col = pctColor(m.pct_change);
  const r = m.reason;
  const reason = r
    ? `<a class="mover-reason" href="${esc(r.link)}" target="_blank" rel="noopener noreferrer">
         <span class="mr-source">${esc(r.source)}</span>${esc(r.title)}</a>`
    : `<div class="mover-reason none">Nessun catalizzatore societario riportato dalle testate seguite</div>`;
  return `<div class="mover">
    <div class="mover-head">
      <span class="sym">${esc(m.symbol)}</span>
      <span class="mname">${esc(m.name)}</span>
      <span class="pct" style="background:${col.bg};color:${col.fg}">${fmtPct(m.pct_change)}</span>
    </div>
    ${reason}
  </div>`;
}

function feedCard(item) {
  const cat = CATEGORIES.find(c => c.key === item.category);
  const dot = `<span class="cat-dot" style="background:var(--cat-${esc(item.category || "mercati")})"></span>`;
  const thumb = item.image
    ? `<div class="feed-thumb"><img src="${esc(item.image)}" alt="" loading="lazy"
         onerror="this.closest('.feed-thumb').classList.add('no-img')"></div>`
    : "";
  const date = (item.published || "").replace(/\\s*\\+?\\d{4}$|\\s*GMT$/, "");
  return `<a class="feed-card" href="${esc(item.link)}" target="_blank" rel="noopener noreferrer">
    ${thumb}
    <div class="feed-card-body">
      <div class="feed-source">${dot}${esc(item.source)}</div>
      <div class="feed-title">${esc(item.title)}</div>
      ${item.summary ? `<div class="feed-summary">${esc(item.summary)}</div>` : ""}
      <div class="feed-date">${esc(date)}${cat ? " &middot; " + esc(cat.label) : ""}</div>
    </div>
  </a>`;
}

function renderEditionHeader(ed) {
  const s = ed.auto_report.stats;
  const autoParas = ed.auto_report.paragraphs.map(p => `<p>${esc(p)}</p>`).join("");
  const commentary = ed.manual_commentary_html
    ? `<div class="commentary">
         <div class="commentary-label">Commento della giornata</div>
         ${ed.manual_commentary_html}
       </div>`
    : "";
  return `
    <div class="eyebrow">Edizione del ${esc(ed.edition_date_it)} <span class="dim">&middot; seduta del ${esc(ed.session_date_it)}</span></div>
    <h2 class="edition-headline">${esc(ed.headline)}</h2>
    <div class="edition-meta">Aggiornato il ${esc(ed.generated_at || "")}</div>

    <div class="stat-strip">
      <div class="stat"><div class="v" style="color:var(--green-4)">${s.n_up}</div><div class="k">In rialzo</div></div>
      <div class="stat"><div class="v" style="color:var(--red-4)">${s.n_down}</div><div class="k">In ribasso</div></div>
      <div class="stat"><div class="v">${s.n_flat}</div><div class="k">Invariate</div></div>
      <div class="stat"><div class="v">${fmtPct(s.avg_pct)}</div><div class="k">Variazione media</div></div>
      <div class="stat"><div class="v">${s.n_total}</div><div class="k">Titoli monitorati</div></div>
    </div>

    <div class="edition-body">
      <div class="edition-text auto-report">${autoParas}${commentary}</div>
      <div class="movers-split">
        <div class="movers-col">
          <h4>Migliori della seduta</h4>
          ${ed.auto_report.gainers.map(moverRow).join("")}
        </div>
        <div class="movers-col">
          <h4>Peggiori della seduta</h4>
          ${ed.auto_report.losers.map(moverRow).join("")}
        </div>
      </div>
    </div>
  `;
}

function renderEditions() {
  const el = document.getElementById("editionsContent");
  if (!EDITIONS.length) {
    el.innerHTML = `<div class="no-edition">Nessuna edizione ancora pubblicata.</div>`;
    return;
  }

  const latest = EDITIONS[0];
  const older = EDITIONS.slice(1);

  const feedItems = latest.feed || [];
  const shown = feedState.category ? feedItems.filter(i => i.category === feedState.category) : feedItems;
  const available = CATEGORIES.filter(c => feedItems.some(i => i.category === c.key));

  let html = `<div class="edition">${renderEditionHeader(latest)}</div>`;

  html += `<div class="section-head">
      <h3>Feed notizie</h3>
      <div class="cat-filters">
        <div class="cat-chip ${feedState.category === null ? "active" : ""}" data-cat="">Tutte (${feedItems.length})</div>
        ${available.map(c => {
          const n = feedItems.filter(i => i.category === c.key).length;
          return `<div class="cat-chip ${feedState.category === c.key ? "active" : ""}" data-cat="${esc(c.key)}">${esc(c.label)} (${n})</div>`;
        }).join("")}
      </div>
    </div>
    <div class="feed-grid">${shown.map(feedCard).join("")}</div>`;

  if (older.length) {
    html += `<div class="section-head" style="margin-top:56px">
        <h3>Archivio edizioni (${older.length})</h3>
        <button class="archive-toggle" id="archiveToggle">${feedState.showArchive ? "Nascondi" : "Mostra"}</button>
      </div>`;
    if (feedState.showArchive) {
      html += older.map(ed => `
        <div class="archive-item">
          <div class="a-date">Edizione del ${esc(ed.edition_date_it)} &middot; seduta del ${esc(ed.session_date_it)}</div>
          <div class="a-title">${esc(ed.headline)}</div>
        </div>
      `).join("");
    }
  }

  el.innerHTML = html;

  el.querySelectorAll(".cat-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      feedState.category = chip.dataset.cat || null;
      renderEditions();
    });
  });
  const at = document.getElementById("archiveToggle");
  if (at) at.addEventListener("click", () => { feedState.showArchive = !feedState.showArchive; renderEditions(); });
}

document.getElementById("gendate").textContent = EDITIONS.length ? EDITIONS[0].edition_date : "n/d";
renderEditions();
</script>
</body>
</html>
"""


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT_DIR
    os.makedirs(out_dir, exist_ok=True)

    editions = load_editions()
    html = TEMPLATE.replace("__EDITIONS_JSON__", json.dumps(editions, ensure_ascii=False))

    out_path = os.path.join(out_dir, "index.html")
    with open(out_path, "w") as f:
        f.write(html)

    size_kb = os.path.getsize(out_path) / 1024
    print(f"Pagina pubblica generata: {out_path} ({size_kb:.0f} KB, {len(editions)} edizioni)")


if __name__ == "__main__":
    main()
