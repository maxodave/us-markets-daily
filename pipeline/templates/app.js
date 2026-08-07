const CATEGORIES = [
  { key: "mercati", label: { it: "Mercati", en: "Markets" } },
  { key: "italia", label: { it: "Italia", en: "Italy" } },
  { key: "crypto", label: { it: "Crypto", en: "Crypto" } },
  { key: "tech", label: { it: "Tech", en: "Tech" } },
  { key: "scienza", label: { it: "Scienza", en: "Science" } },
];
let feedState = { category: null, showArchive: false };

// Lingua e scheda-indice, persistite: un lettore che torna ritrova la sua scelta.
// L'inglese e' la lingua originale/di default (vedi README).
let lang = localStorage.getItem("lang") || "en";
let indexTab = localStorage.getItem("indexTab") || "sp500";
const INDEX_TABS = ["sp500", "dow", "nasdaq100", "combined"];
const INDEX_BADGE = { sp500: "SPX", dow: "DJI", nasdaq100: "NDX" };

const I18N = {
  en: {
    subtitle: "Daily report on US markets",
    disclaimerHtml: `<b>Research/monitoring only.</b> No investment advice, no trades executed.
    Market data via Yahoo Finance, news via outlets' public feeds
    (Reuters, Bloomberg, FT, WSJ, CNBC, MarketWatch, Barron's, NYT, Forbes, Yahoo Finance and others).
    Every buy/sell decision remains entirely yours.`,
    footer: "Images remain the property of their respective outlets, linked to the original source.",
    noEdition: "No edition published yet.",
    feedTitle: "News feed",
    allLabel: "All",
    archiveLabel: "Edition archive",
    archiveShow: "Show",
    archiveHide: "Hide",
    editionOf: "Edition of",
    sessionOf: "session of",
    updatedOn: "Updated on",
    statUp: "Higher",
    statDown: "Lower",
    statFlat: "Unchanged",
    statAvg: "Average move",
    statTotal: "Stocks tracked",
    bestMovers: "Best of the session",
    worstMovers: "Worst of the session",
    noCatalyst: "No company-specific catalyst reported by the outlets tracked",
    commentaryLabel: "Today's commentary",
    indexLabels: { sp500: "S&P 500", dow: "Dow Jones", nasdaq100: "Nasdaq-100", combined: "Combined" },
  },
  it: {
    subtitle: "Resoconto giornaliero dei mercati USA",
    disclaimerHtml: `<b>Solo ricerca/monitoraggio.</b> Nessun consiglio di investimento, nessuna operazione eseguita.
    Dati di mercato via Yahoo Finance, notizie via feed pubblici delle testate
    (Reuters, Bloomberg, FT, WSJ, CNBC, MarketWatch, Barron's, NYT, Forbes, Yahoo Finance e altre).
    Ogni decisione di acquisto/vendita resta esclusivamente tua.`,
    footer: "Le immagini restano di proprieta' delle rispettive testate, linkate alla fonte originale.",
    noEdition: "Nessuna edizione ancora pubblicata.",
    feedTitle: "Feed notizie",
    allLabel: "Tutte",
    archiveLabel: "Archivio edizioni",
    archiveShow: "Mostra",
    archiveHide: "Nascondi",
    editionOf: "Edizione del",
    sessionOf: "seduta del",
    updatedOn: "Aggiornato il",
    statUp: "In rialzo",
    statDown: "In ribasso",
    statFlat: "Invariate",
    statAvg: "Variazione media",
    statTotal: "Titoli monitorati",
    bestMovers: "Migliori della seduta",
    worstMovers: "Peggiori della seduta",
    noCatalyst: "Nessun catalizzatore societario riportato dalle testate seguite",
    commentaryLabel: "Commento della giornata",
    indexLabels: { sp500: "S&P 500", dow: "Dow Jones", nasdaq100: "Nasdaq-100", combined: "Combinata" },
  },
};

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]));
}
// lang di default "it": le chiamate della vista LEGACY (edizioni pre-multi-indice,
// vedi renderEditionHeaderLegacy) non passano un argomento e devono continuare a
// dare la virgola decimale italiana, esattamente come prima di questa modifica.
function fmtPct(v, lang = "it") {
  const s = (v > 0 ? "+" : "") + Number(v).toFixed(2) + "%";
  return lang === "it" ? s.replace(".", ",") : s;
}

function pctColor(pct) {
  if (pct <= -5) return { bg: "var(--red-3)", fg: "#fff" };
  if (pct < 0) return { bg: "var(--red-1)", fg: "var(--red-5)" };
  if (pct <= 2.5) return { bg: "var(--green-1)", fg: "var(--green-5)" };
  if (pct <= 10) return { bg: "var(--green-2)", fg: "var(--green-5)" };
  if (pct <= 20) return { bg: "var(--green-3)", fg: "#fff" };
  return { bg: "var(--green-4)", fg: "#0b0d12" };
}

function moverRow(m, lang = "it", showBadge = false) {
  const col = pctColor(m.pct_change);
  const r = m.reason;
  const t = I18N[lang];
  const reason = r
    ? `<a class="mover-reason" href="${esc(r.link)}" target="_blank" rel="noopener noreferrer">
         <span class="mr-source">${esc(r.source)}</span>${esc(r.title)}</a>`
    : `<div class="mover-reason none">${esc(t.noCatalyst)}</div>`;
  // Il badge indice serve solo nella scheda "Combined": altrove il titolo e' gia'
  // nella lista di UN indice, quindi l'indice e' implicito e il badge sarebbe rumore.
  const badge = showBadge && m.indices && m.indices.length
    ? `<span class="index-badge">${m.indices.map(i => esc(INDEX_BADGE[i] || i)).join(" ")}</span>`
    : "";
  return `<div class="mover">
    <div class="mover-head">
      <span class="sym">${esc(m.symbol)}</span>
      <span class="mname">${esc(m.name)}</span>
      ${badge}
      <span class="pct" style="background:${col.bg};color:${col.fg}">${fmtPct(m.pct_change, lang)}</span>
    </div>
    ${reason}
  </div>`;
}

function feedCard(item, lang = "it") {
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
      <div class="feed-date">${esc(date)}${cat ? " &middot; " + esc(cat.label[lang]) : ""}</div>
    </div>
  </a>`;
}

// ====== Vista LEGACY: edizioni create prima del multi-indice/bilingue ======
// Copia esatta del rendering di sempre. Non tocca ne' lang ne' indexTab: le
// edizioni del 5-7 agosto 2026 (e ogni edizione senza "auto_report_by_index")
// devono continuare ad apparire cosi' com'erano, senza pulsante lingua ne' schede.
function renderEditionHeaderLegacy(ed) {
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
          ${ed.auto_report.gainers.map(m => moverRow(m)).join("")}
        </div>
        <div class="movers-col">
          <h4>Peggiori della seduta</h4>
          ${ed.auto_report.losers.map(m => moverRow(m)).join("")}
        </div>
      </div>
    </div>
  `;
}

// ====== Vista NUOVA: bilingue + 3 indici + combinata ======
function renderEditionHeaderNew(ed, lang, indexTab) {
  const t = I18N[lang];
  const block = ed.auto_report_by_index[indexTab] || ed.auto_report_by_index.sp500;
  const s = block.stats;
  const paragraphs = (block.paragraphs && block.paragraphs[lang]) || [];
  const autoParas = paragraphs.map(p => `<p>${esc(p)}</p>`).join("");

  const commentaryHtml = lang === "it" ? ed.manual_commentary_html : ed.manual_commentary_html_en;
  const commentary = commentaryHtml
    ? `<div class="commentary">
         <div class="commentary-label">${esc(t.commentaryLabel)}</div>
         ${commentaryHtml}
       </div>`
    : "";

  // Le edizioni piu' vecchie in archivio potrebbero non avere ancora il campo
  // *_en (le prime edizioni bilingui): si ricade sull'italiano invece di mostrare
  // un buco. Per l'edizione in testa (quella con auto_report_by_index) questo non
  // scatta mai, perche' entrambe le lingue si generano sempre insieme.
  const editionDate = lang === "en" ? (ed.edition_date_en || ed.edition_date_it) : ed.edition_date_it;
  const sessionDate = lang === "en" ? (ed.session_date_en || ed.session_date_it) : ed.session_date_it;
  const headline = lang === "en" ? (ed.headline_en || ed.headline) : ed.headline;

  const langToggle = `<div class="lang-toggle">
      <div class="lang-chip ${lang === "en" ? "active" : ""}" data-lang="en">EN</div>
      <div class="lang-chip ${lang === "it" ? "active" : ""}" data-lang="it">IT</div>
    </div>`;

  const indexTabsHtml = `<div class="index-tabs">
      ${INDEX_TABS.map(k => `<div class="index-chip ${indexTab === k ? "active" : ""}" data-index="${k}">${esc(t.indexLabels[k])}</div>`).join("")}
    </div>`;

  return `
    <div class="eyebrow-row">
      <div class="eyebrow">${esc(t.editionOf)} ${esc(editionDate)} <span class="dim">&middot; ${esc(t.sessionOf)} ${esc(sessionDate)}</span></div>
      ${langToggle}
    </div>
    <h2 class="edition-headline">${esc(headline)}</h2>
    <div class="edition-meta">${esc(t.updatedOn)} ${esc(ed.generated_at || "")}</div>

    <div class="stat-strip">
      <div class="stat"><div class="v" style="color:var(--green-4)">${s.n_up}</div><div class="k">${esc(t.statUp)}</div></div>
      <div class="stat"><div class="v" style="color:var(--red-4)">${s.n_down}</div><div class="k">${esc(t.statDown)}</div></div>
      <div class="stat"><div class="v">${s.n_flat}</div><div class="k">${esc(t.statFlat)}</div></div>
      <div class="stat"><div class="v">${fmtPct(s.avg_pct, lang)}</div><div class="k">${esc(t.statAvg)}</div></div>
      <div class="stat"><div class="v">${s.n_total}</div><div class="k">${esc(t.statTotal)}</div></div>
    </div>

    ${indexTabsHtml}

    <div class="edition-body">
      <div class="edition-text auto-report">${autoParas}${commentary}</div>
      <div class="movers-split">
        <div class="movers-col">
          <h4>${esc(t.bestMovers)}</h4>
          ${block.gainers.map(m => moverRow(m, lang, indexTab === "combined")).join("")}
        </div>
        <div class="movers-col">
          <h4>${esc(t.worstMovers)}</h4>
          ${block.losers.map(m => moverRow(m, lang, indexTab === "combined")).join("")}
        </div>
      </div>
    </div>
  `;
}

// Testo fisso fuori da #editionsContent (sottotitolo/disclaimer/footer): segue la
// stessa lingua effettiva della vista, calcolata una sola volta in renderEditions().
function applyShellI18n(effectiveLang) {
  const t = I18N[effectiveLang];
  const subtitleEl = document.getElementById("subtitle-text");
  const disclaimerEl = document.getElementById("disclaimer-text");
  const footerEl = document.getElementById("footer-text");
  if (subtitleEl) subtitleEl.textContent = t.subtitle;
  if (disclaimerEl) disclaimerEl.innerHTML = t.disclaimerHtml;
  if (footerEl) footerEl.textContent = t.footer;
}

function renderEditions() {
  const el = document.getElementById("editionsContent");
  if (!EDITIONS.length) {
    applyShellI18n(lang);
    el.innerHTML = `<div class="no-edition">${esc(I18N[lang].noEdition)}</div>`;
    return;
  }

  const latest = EDITIONS[0];
  const older = EDITIONS.slice(1);
  const hasMultiIndex = !!latest.auto_report_by_index;
  // Le edizioni pre-multi-indice non hanno testo inglese: quando sono in testa,
  // TUTTA la pagina (non solo l'edizione) resta in italiano, senza pulsante
  // lingua ne' schede — esattamente come prima di questa funzionalita'.
  const L = hasMultiIndex ? lang : "it";
  const t = I18N[L];
  applyShellI18n(L);

  const feedItems = latest.feed || [];
  const shown = feedState.category ? feedItems.filter(i => i.category === feedState.category) : feedItems;
  const available = CATEGORIES.filter(c => feedItems.some(i => i.category === c.key));

  const header = hasMultiIndex ? renderEditionHeaderNew(latest, lang, indexTab) : renderEditionHeaderLegacy(latest);
  let html = `<div class="edition">${header}</div>`;

  html += `<div class="section-head">
      <h3>${esc(t.feedTitle)}</h3>
      <div class="cat-filters">
        <div class="cat-chip ${feedState.category === null ? "active" : ""}" data-cat="">${esc(t.allLabel)} (${feedItems.length})</div>
        ${available.map(c => {
          const n = feedItems.filter(i => i.category === c.key).length;
          return `<div class="cat-chip ${feedState.category === c.key ? "active" : ""}" data-cat="${esc(c.key)}">${esc(c.label[L])} (${n})</div>`;
        }).join("")}
      </div>
    </div>
    <div class="feed-grid">${shown.map(item => feedCard(item, L)).join("")}</div>`;

  if (older.length) {
    html += `<div class="section-head" style="margin-top:56px">
        <h3>${esc(t.archiveLabel)} (${older.length})</h3>
        <button class="archive-toggle" id="archiveToggle">${feedState.showArchive ? esc(t.archiveHide) : esc(t.archiveShow)}</button>
      </div>`;
    if (feedState.showArchive) {
      html += older.map(ed => {
        const edDate = L === "en" ? (ed.edition_date_en || ed.edition_date_it) : ed.edition_date_it;
        const sDate = L === "en" ? (ed.session_date_en || ed.session_date_it) : ed.session_date_it;
        const headline = L === "en" ? (ed.headline_en || ed.headline) : ed.headline;
        return `
        <div class="archive-item">
          <div class="a-date">${esc(t.editionOf)} ${esc(edDate)} &middot; ${esc(t.sessionOf)} ${esc(sDate)}</div>
          <div class="a-title">${esc(headline)}</div>
        </div>
      `;
      }).join("");
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

  if (hasMultiIndex) {
    el.querySelectorAll(".lang-chip").forEach(chip => {
      chip.addEventListener("click", () => {
        lang = chip.dataset.lang;
        localStorage.setItem("lang", lang);
        renderEditions();
      });
    });
    el.querySelectorAll(".index-chip").forEach(chip => {
      chip.addEventListener("click", () => {
        indexTab = chip.dataset.index;
        localStorage.setItem("indexTab", indexTab);
        renderEditions();
      });
    });
  }
}

document.getElementById("gendate").textContent = EDITIONS.length ? EDITIONS[0].edition_date : "n/d";
renderEditions();
