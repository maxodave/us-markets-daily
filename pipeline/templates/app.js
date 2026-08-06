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
  // [+-] e non \+? : i fusi negativi ("... 17:41:36 -0400") lasciavano un "-" orfano.
  const date = (item.published || "").replace(/\s*[+-]?\d{4}$|\s*GMT$/, "");
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
