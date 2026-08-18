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
const INDEX_TABS = ["sp500", "dow", "nasdaq100", "ftsemib", "combined"];
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
    moverNewsTitle: "The news behind the movers",
    liveMoversTop: "Top 10 movers",
    liveMoversWorst: "Worst 10 movers",
    liveMoversNow: "now",
    liveMoversClose: "last close",
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
    marketsBriefLabel: "Top in Markets",
    indexLabels: { sp500: "S&P 500", dow: "Dow Jones", nasdaq100: "Nasdaq-100", ftsemib: "FTSE MIB", combined: "Combined" },
    // Edizione senza seduta nuova (domenica, lunedi', dopo una festivita').
    newsFrom: "news from",
    noSessionNote: "Wall Street was closed. The last session was covered in the previous edition and its figures are not repeated here.",
    signalsTitle: "What traded while Wall Street was closed",
    signalsNote: "Change since the last US close. These are quotes on markets that stay open — not forecasts.",
    watchTitle: "On the calendar",
    watchNote: "Scheduled events and previews published by the outlets themselves — listed, not predicted.",
    digestTitle: "The weekend in headlines",
    moreTitle: "More from these days",
    weekendCommentaryLabel: "Weekend commentary",
    nicheTitle: "Named in weekend coverage",
    nicheNote: "A lexical score (0–10) for how intensely the outlets themselves wrote about it — not a forecast, not investment advice, and not backtested against real price moves.",
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
    moverNewsTitle: "Le notizie dietro i mover",
    liveMoversTop: "Migliori 10",
    liveMoversWorst: "Peggiori 10",
    liveMoversNow: "ora",
    liveMoversClose: "ultima chiusura",
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
    marketsBriefLabel: "Top Mercati",
    indexLabels: { sp500: "S&P 500", dow: "Dow Jones", nasdaq100: "Nasdaq-100", ftsemib: "FTSE MIB", combined: "Combinata" },
    newsFrom: "notizie del",
    noSessionNote: "Wall Street era chiusa. L'ultima seduta e' gia' stata coperta dall'edizione precedente: i suoi numeri qui non vengono ripetuti.",
    signalsTitle: "Cosa ha scambiato a Wall Street chiusa",
    signalsNote: "Variazione dall'ultima chiusura americana. Sono quotazioni di mercati rimasti aperti, non previsioni.",
    watchTitle: "In calendario",
    watchNote: "Appuntamenti gia' fissati e anteprime pubblicate dalle testate stesse: elencati, non previsti.",
    digestTitle: "Il fine settimana in sintesi",
    moreTitle: "Altre notizie di questi giorni",
    weekendCommentaryLabel: "Commento del fine settimana",
    nicheTitle: "Nominate nella copertura del weekend",
    nicheNote: "Un punteggio lessicale (0–10) su quanto intensamente ne hanno scritto le testate — non una previsione, non un consiglio di investimento, non verificato contro i movimenti di prezzo reali.",
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
// Riga laterale "Top Mercati": bordo colorato (viola nei giorni di borsa,
// arancione nel weekend) con il riassunto delle notizie top della sezione
// Mercati. Preferisce la prosa scritta da Claude; se non c'e', elenca i titoli
// top (sempre presenti), cosi' il blocco non e' mai vuoto. Vedi build_edition.py.
function marketsBrief(ed, lang, isWeekend) {
  const mb = ed.markets_brief;
  if (!mb) return "";
  const t = I18N[lang];
  const prose = lang === "en" ? mb.prose_html_en : mb.prose_html;
  const items = mb.items || [];
  if (!prose && !items.length) return "";
  const body = prose
    ? `<div class="mb-prose">${prose}</div>`
    : `<ul class="mb-list">${items.map(i =>
        `<li><a href="${esc(i.link)}" target="_blank" rel="noopener noreferrer"><span class="mb-src">${esc(i.source)}</span>${esc(i.title)}</a></li>`
      ).join("")}</ul>`;
  return `<div class="markets-brief${isWeekend ? " weekend" : ""}">
      <div class="mb-label">${esc(t.marketsBriefLabel)}</div>
      ${body}
    </div>`;
}

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
      <div class="edition-text auto-report">${autoParas}${marketsBrief(ed, lang, false)}${commentary}</div>
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

// ====== Vista FINE SETTIMANA: nessuna seduta nuova da raccontare ======
// Domenica, lunedi' e il giorno dopo una festivita' di borsa l'ultima seduta
// chiusa e' la stessa gia' pubblicata: ripeterne percentuali, top gainer e top
// loser per tre giorni di fila e' inutile per chi legge. Questa vista mostra
// invece il riassunto delle notizie del giorno appena passato, i mercati che
// restano aperti e gli appuntamenti in calendario. Vedi weekend_edition.py.
//
// Volutamente NON disegna: stat-strip della seduta, schede indice, elenchi di
// mover. Se un giorno ricomparissero qui, sarebbe tornato il difetto.

// I movimenti macro non si leggono con la scala di un singolo titolo: per un
// future sull'S&P 500 lo 0,8% e' una giornata vera, per un'azione e' rumore.
// Da qui una scala propria, molto piu' stretta di pctColor().
function signalColor(pct) {
  const a = Math.abs(pct);
  if (a < 0.25) return { bg: "var(--panel-2)", fg: "var(--muted)" };
  if (pct > 0) return a < 1 ? { bg: "var(--green-1)", fg: "var(--green-5)" } : { bg: "var(--green-3)", fg: "#fff" };
  return a < 1 ? { bg: "var(--red-1)", fg: "var(--red-5)" } : { bg: "var(--red-3)", fg: "#fff" };
}

function signalPanel(signals, lang) {
  if (!signals || !signals.groups || !signals.groups.length) return "";
  const t = I18N[lang];
  const groups = signals.groups.map(g => `
    <div class="signal-group">
      <div class="sg-label">${esc(g.label[lang] || g.label.en)}</div>
      ${g.instruments.map(i => {
        const c = signalColor(i.pct_change);
        const name = lang === "it" ? (i.name_it || i.name_en) : i.name_en;
        return `<div class="signal-row">
          <span class="sig-name">${esc(name)}</span>
          <span class="pct" style="background:${c.bg};color:${c.fg}">${fmtPct(i.pct_change, lang)}</span>
        </div>`;
      }).join("")}
    </div>`).join("");
  return `<div class="signal-panel">
    <div class="signal-head">
      <h4>${esc(t.signalsTitle)}</h4>
      <div class="signal-note">${esc(t.signalsNote)}</div>
    </div>
    <div class="signal-grid">${groups}</div>
  </div>`;
}

// Punteggio 0-10 -> colore. Volutamente NEUTRO (mai rosso/verde): in questo
// sito rosso e verde significano sempre "il prezzo e' sceso/salito", ma questo
// punteggio non ha una direzione — un richiamo prodotti e un utile record
// possono avere lo stesso punteggio alto, perche' misura solo quanto
// intensamente ne ha scritto la testata. Colorarlo come una percentuale
// smentirebbe in un'occhiata cio' che nicheNote dice a parole.
function scoreColor(score) {
  if (score >= 8) return { bg: "var(--accent)", fg: "#fff" };
  if (score >= 6.5) return { bg: "var(--panel-2)", fg: "var(--accent)" };
  return { bg: "var(--panel-2)", fg: "var(--muted)" };
}

function nichePanel(signals, lang) {
  if (!signals || !signals.length) return "";
  const t = I18N[lang];
  const rows = signals.map(s => {
    const c = scoreColor(s.score);
    return `<a class="niche-item" href="${esc(s.link)}" target="_blank" rel="noopener noreferrer">
      <div class="niche-head">
        <span class="sym">${esc(s.symbol)}</span>
        <span class="mname">${esc(s.name)}</span>
        <span class="score-badge" style="background:${c.bg};color:${c.fg}">${s.score}/10</span>
      </div>
      <div class="mover-reason"><span class="mr-source">${esc(s.source)}</span>${esc(s.title)}</div>
    </a>`;
  }).join("");
  return `<div class="watch-col">
    <h4>${esc(t.nicheTitle)}</h4>
    ${rows}
    <div class="watch-note">${esc(t.nicheNote)}</div>
  </div>`;
}

function watchPanel(watchlist, lang) {
  if (!watchlist || !watchlist.length) return "";
  const t = I18N[lang];
  const rows = watchlist.map(w => `
    <a class="watch-item" href="${esc(w.link)}" target="_blank" rel="noopener noreferrer">
      <span class="mr-source">${esc(w.source)}</span>${esc(w.title)}
    </a>`).join("");
  return `<div class="watch-col">
    <h4>${esc(t.watchTitle)}</h4>
    ${rows}
    <div class="watch-note">${esc(t.watchNote)}</div>
  </div>`;
}

function renderEditionHeaderWeekend(ed, lang) {
  const t = I18N[lang];
  const w = ed.weekend_report;
  const paragraphs = (w.paragraphs && w.paragraphs[lang]) || [];
  const autoParas = paragraphs.map(p => `<p>${esc(p)}</p>`).join("");

  const commentaryHtml = lang === "it" ? ed.weekend_commentary_html : ed.weekend_commentary_html_en;
  const commentary = commentaryHtml
    ? `<div class="commentary">
         <div class="commentary-label">${esc(t.weekendCommentaryLabel)}</div>
         ${commentaryHtml}
       </div>`
    : "";

  const editionDate = lang === "en" ? (ed.edition_date_en || ed.edition_date_it) : ed.edition_date_it;
  const coversDate = lang === "en" ? w.covers_date_en : w.covers_date_it;
  const headline = lang === "en" ? (ed.headline_en || ed.headline) : ed.headline;

  const langToggle = `<div class="lang-toggle">
      <div class="lang-chip ${lang === "en" ? "active" : ""}" data-lang="en">EN</div>
      <div class="lang-chip ${lang === "it" ? "active" : ""}" data-lang="it">IT</div>
    </div>`;

  return `
    <div class="eyebrow-row">
      <div class="eyebrow">${esc(t.editionOf)} ${esc(editionDate)} <span class="dim">&middot; ${esc(t.newsFrom)} ${esc(coversDate)}</span></div>
      ${langToggle}
    </div>
    <h2 class="edition-headline">${esc(headline)}</h2>
    <div class="edition-meta">${esc(t.updatedOn)} ${esc(ed.generated_at || "")}</div>

    <div class="no-session-note">${esc(t.noSessionNote)}</div>

    ${signalPanel(w.signals, lang)}

    <div class="edition-body">
      <div class="edition-text auto-report">${autoParas}${marketsBrief(ed, lang, true)}${commentary}</div>
      <div class="weekend-side">
        ${watchPanel(w.watchlist, lang)}
        ${nichePanel(w.niche_signals, lang)}
      </div>
    </div>
  `;
}

function weekendDigest(w, lang) {
  if (!w.sections || !w.sections.length) return "";
  const t = I18N[lang];
  let html = `<div class="section-head"><h3>${esc(t.digestTitle)}</h3></div>`;
  w.sections.forEach(s => {
    // Solo il nome del tema: mostrare accanto il totale disponibile (59) sopra
    // sei schede fa sembrare la pagina incompleta. I totali stanno nel testo,
    // dove sono una misura di copertura e non una promessa non mantenuta.
    html += `<div class="digest-theme">${esc(s.label[lang] || s.label.en)}</div>`;
    html += `<div class="feed-grid">${s.items.map(i => feedCard(i, lang)).join("")}</div>`;
  });
  return html;
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

// "Le notizie dietro i mover": i catalizzatori dei top gainer/loser della seduta,
// in cima a "Tutte". Sono gli stessi articoli-motivazione gia' scelti da
// mover_reason.py (fonte affidabile, recente, specifica sul titolo): qui li
// raccogliamo da tutti gli indici, deduplicati per titolo e ordinati per ampiezza
// del movimento, cosi' la sera e la mattina si capisce PERCHE' un titolo e' salito
// o sceso, prima di decidere long o short. Se un mover non ha un catalizzatore
// affidabile, semplicemente non compare (niente motivazioni inventate).
function moverNewsHtml(ed, lang) {
  const t = I18N[lang];
  const byIdx = ed.auto_report_by_index;
  if (!byIdx) return "";  // edizioni weekend/legacy: nessun mover da spiegare
  const block = byIdx.combined || byIdx.sp500;
  if (!block) return "";
  const seen = new Set();
  const picks = [];
  [...(block.gainers || []), ...(block.losers || [])].forEach(m => {
    if (!m.reason || seen.has(m.symbol)) return;
    seen.add(m.symbol);
    picks.push(m);
  });
  if (!picks.length) return "";
  picks.sort((a, b) => Math.abs(b.pct_change) - Math.abs(a.pct_change));
  const cards = picks.map(m => {
    const col = pctColor(m.pct_change);
    const r = m.reason;
    return `<a class="mn-card" href="${esc(r.link)}" target="_blank" rel="noopener noreferrer">
      <div class="mn-head">
        <span class="mn-sym">${esc(m.symbol)}</span>
        <span class="mn-name">${esc(m.name)}</span>
        <span class="mn-pct" style="background:${col.bg};color:${col.fg}">${fmtPct(m.pct_change, lang)}</span>
      </div>
      <div class="mn-title"><span class="mn-src">${esc(r.source)}</span>${esc(r.title)}</div>
    </a>`;
  }).join("");
  return `<div class="mover-news">
      <div class="section-head"><h3>${esc(t.moverNewsTitle)}</h3></div>
      <div class="mn-grid">${cards}</div>
    </div>`;
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
  // Un'edizione di riassunto ha comunque auto_report_by_index (e' l'archivio dei
  // dati della seduta), quindi il controllo va fatto PRIMA: qui si sceglie che
  // cosa disegnare, e per il fine settimana la risposta non e' "la seduta".
  const isWeekend = latest.edition_kind === "weekend_recap" && !!latest.weekend_report;
  // Le edizioni pre-multi-indice non hanno testo inglese: quando sono in testa,
  // TUTTA la pagina (non solo l'edizione) resta in italiano, senza pulsante
  // lingua ne' schede — esattamente come prima di questa funzionalita'.
  const L = (hasMultiIndex || isWeekend) ? lang : "it";
  const t = I18N[L];
  applyShellI18n(L);

  const feedItems = latest.feed || [];
  const shown = feedState.category ? feedItems.filter(i => i.category === feedState.category) : feedItems;
  const available = CATEGORIES.filter(c => feedItems.some(i => i.category === c.key));

  const header = isWeekend
    ? renderEditionHeaderWeekend(latest, L)
    : (hasMultiIndex ? renderEditionHeaderNew(latest, lang, indexTab) : renderEditionHeaderLegacy(latest));
  // DUE VISTE distinte, scelte dalla nav via body[data-view]:
  //  - "edition" = l'editoriale (statistiche, movers, Top Mercati, commento) +
  //    l'archivio: il notiziario del giorno, come lo screenshot dell'edizione.
  //  - "live" = la striscia indici LIVE + il feed di notizie del giorno.
  // Si disegnano SEMPRE entrambi i pannelli; la CSS ne mostra uno solo, cosi' il
  // cambio vista non ridisegna nulla (la striscia LIVE mantiene i suoi dati).
  let editorial = `<div class="edition">${header}</div>`;
  if (isWeekend) editorial += weekendDigest(latest.weekend_report, L);
  // Edizione di seduta: sotto l'editoriale, il feed "notizie dietro i mover" con i
  // catalizzatori dei 10 top gainer e 10 top loser (una scheda per titolo, i piu'
  // forti prima). E' lo stesso blocco che compare in LIVE; qui resta dalla chiusura
  // della sera fino alla nuova edizione. La vista LIVE non viene toccata.
  else editorial += moverNewsHtml(latest, L);

  let archiveHtml = "";
  if (older.length) {
    archiveHtml = `<div class="section-head" style="margin-top:56px">
        <h3>${esc(t.archiveLabel)} (${older.length})</h3>
        <button class="archive-toggle" id="archiveToggle">${feedState.showArchive ? esc(t.archiveHide) : esc(t.archiveShow)}</button>
      </div>`;
    if (feedState.showArchive) {
      archiveHtml += older.map(ed => {
        const edDate = L === "en" ? (ed.edition_date_en || ed.edition_date_it) : ed.edition_date_it;
        const headline = L === "en" ? (ed.headline_en || ed.headline) : ed.headline;
        // Le edizioni del fine settimana si datano sulle NOTIZIE che riassumono,
        // non sulla seduta: scritte "seduta del 14 agosto" apparirebbero come tre
        // voci identiche in fila, che e' esattamente cio' che si voleva togliere.
        const weekend = ed.edition_kind === "weekend_recap";
        const subLabel = weekend ? t.newsFrom : t.sessionOf;
        const sDate = weekend
          ? (L === "en" ? (ed.covers_date_en || ed.covers_date_it) : ed.covers_date_it)
          : (L === "en" ? (ed.session_date_en || ed.session_date_it) : ed.session_date_it);
        return `
        <div class="archive-item">
          <div class="a-date">${esc(t.editionOf)} ${esc(edDate)} &middot; ${esc(subLabel)} ${esc(sDate)}</div>
          <div class="a-title">${esc(headline)}</div>
        </div>
      `;
      }).join("");
    }
  }

  // Scheda LIVE: al posto delle "notizie dietro i mover" (che ora vivono SOLO
  // nell'edizione) va la lista dei top 10 / worst 10 del MOMENTO. Il contenitore
  // resta vuoto qui: lo riempie il poller di live.json (funzione live() sotto),
  // cosi' cambia a ogni aggiornamento (ogni 15 min) come lo striscione in basso.
  // A mercati chiusi ricade sui mover della seduta. Nel weekend non c'e' seduta.
  const liveMoversSlot = isWeekend ? "" : `<div id="liveMovers" class="live-movers"></div>`;

  const feedHtml = liveMoversSlot + `<div class="section-head">
      <h3>${esc(isWeekend ? t.moreTitle : t.feedTitle)}</h3>
      <div class="cat-filters">
        <div class="cat-chip ${feedState.category === null ? "active" : ""}" data-cat="">${esc(t.allLabel)} (${feedItems.length})</div>
        ${available.map(c => {
          const n = feedItems.filter(i => i.category === c.key).length;
          return `<div class="cat-chip ${feedState.category === c.key ? "active" : ""}" data-cat="${esc(c.key)}">${esc(c.label[L])} (${n})</div>`;
        }).join("")}
      </div>
    </div>
    <div class="feed-grid">${shown.map(item => feedCard(item, L)).join("")}</div>`;

  const html = `<div class="only-edition">${editorial}${archiveHtml}</div>`
             + `<div class="only-live">${feedHtml}</div>`;

  el.innerHTML = html;

  el.querySelectorAll(".cat-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      feedState.category = chip.dataset.cat || null;
      renderEditions();
    });
  });
  const at = document.getElementById("archiveToggle");
  if (at) at.addEventListener("click", () => { feedState.showArchive = !feedState.showArchive; renderEditions(); });

  if (hasMultiIndex || isWeekend) {
    el.querySelectorAll(".lang-chip").forEach(chip => {
      chip.addEventListener("click", () => {
        lang = chip.dataset.lang;
        localStorage.setItem("lang", lang);
        renderEditions();
      });
    });
    // Le schede indice esistono solo nella vista di seduta: nel fine settimana
    // non c'e' nessun elenco per indice da filtrare, quindi il selettore non
    // viene disegnato e questo ciclo non trova nulla.
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

// ====== Layer cinematografico: hero, viste LIVE/edition, weekend, quotazioni ======
// Solo presentazione e navigazione: nessun dato nuovo oltre a live.json (le
// quotazioni degli indici, raccolte da un workflow perche' il browser non puo'
// leggere Yahoo per via del CORS). Tutto degrada con grazia se un pezzo manca.
(function heroLayer() {
  var HEADER_H = 64;
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* --- mover del MOMENTO: da live.json se il mercato e' aperto e li ha, altrimenti
         i mover della SEDUTA dall'edizione (a mercato chiuso). Stessa identica fonte
         per lo striscione in basso e per la lista nella scheda LIVE, cosi' coincidono
         sempre e cambiano insieme a ogni refresh di live.json (~15 min). --- */
  function moversFor(live) {
    if (live && live.market_open && live.movers && (live.movers.gainers || []).length) {
      var mapL = function (m) { return { s: m.symbol, p: m.pct, n: m.name || "" }; };
      return { live: true, gainers: live.movers.gainers.map(mapL), losers: (live.movers.losers || []).map(mapL) };
    }
    if (typeof EDITIONS !== "undefined" && EDITIONS.length) {
      var ed = EDITIONS[0];
      var blk = ed.auto_report_by_index ? (ed.auto_report_by_index.combined || ed.auto_report_by_index.sp500) : ed.auto_report;
      if (blk && (blk.gainers || []).length) {
        var mapE = function (m) { return { s: m.symbol, p: m.pct_change, n: m.name || "" }; };
        return { live: false, gainers: (blk.gainers || []).slice(0, 10).map(mapE), losers: (blk.losers || []).slice(0, 10).map(mapE) };
      }
      if (ed.weekend_report && ed.weekend_report.signals) {
        var rows = [];
        (ed.weekend_report.signals.groups || []).forEach(function (g) { (g.instruments || []).forEach(function (it) { rows.push({ s: it.name_en || it.name, p: it.pct_change, n: "" }); }); });
        return { live: false, gainers: rows, losers: [] };
      }
    }
    return { live: false, gainers: [], losers: [] };
  }

  function renderTicker(live) {
    var track = document.getElementById("tickerTrack"), bar = document.getElementById("tickerBar");
    if (!track || !bar) return;
    var mv = moversFor(live), rows = mv.gainers.concat(mv.losers);
    if (!rows.length) { bar.style.display = "none"; document.body.style.paddingBottom = "0"; return; }
    bar.style.display = "";
    var cell = function (r) { var cls = r.p >= 0 ? "up" : "down", sign = r.p >= 0 ? "+" : ""; return '<span class="tk"><span class="sym">' + r.s + '</span><span class="' + cls + '">' + sign + Number(r.p).toFixed(2) + '%</span></span>'; };
    var h = rows.map(cell).join(""); track.innerHTML = h + h;
  }

  function paintLiveMovers(live) {
    var box = document.getElementById("liveMovers"); if (!box) return;
    var mv = moversFor(live);
    if (!mv.gainers.length && !mv.losers.length) { box.innerHTML = ""; return; }
    var t = I18N[lang], tag = mv.live ? t.liveMoversNow : t.liveMoversClose;
    var col = function (label, list, dir) {
      var body = list.map(function (r) {
        var cls = r.p >= 0 ? "up" : "down", sign = r.p >= 0 ? "+" : "";
        return '<div class="lm-row"><span class="lm-sym">' + r.s + '</span><span class="lm-name">' + r.n + '</span><span class="lm-pct ' + cls + '">' + sign + Number(r.p).toFixed(2) + '%</span></div>';
      }).join("");
      return '<div class="lm-col"><div class="lm-head ' + dir + '">' + label + ' <span class="lm-tag">&middot; ' + tag + '</span></div>' + body + '</div>';
    };
    box.innerHTML = col(t.liveMoversTop, mv.gainers, "up") + col(t.liveMoversWorst, mv.losers, "down");
  }

  /* --- campo stellare --- */
  (function stars() {
    var c = document.getElementById("stars"); if (!c || reduce) return;
    var x = c.getContext("2d"); if (!x) return;
    var W, H, st, mx = 0, my = 0, t = 0, raf;
    function rs() { W = c.width = innerWidth; H = c.height = innerHeight; var n = Math.min(180, Math.floor(W * H / 12000));
      st = Array.from({ length: n }, function () { return { x: Math.random() * W, y: Math.random() * H, z: Math.random() * .8 + .2, r: Math.random() * 1.2 + .2, tw: Math.random() * Math.PI * 2 }; }); }
    function draw() { t += .012; x.clearRect(0, 0, W, H); for (var i = 0; i < st.length; i++) { var s = st[i]; var px = s.x + mx * 24 * s.z, py = s.y + my * 24 * s.z, a = .28 + Math.sin(t + s.tw) * .22; x.beginPath(); x.arc(px, py, s.r * s.z * 1.3, 0, 7); x.fillStyle = "rgba(200,214,255," + a.toFixed(2) + ")"; x.fill(); } raf = requestAnimationFrame(draw); }
    rs(); draw(); addEventListener("resize", rs); addEventListener("mousemove", function (e) { mx = e.clientX / W - .5; my = e.clientY / H - .5; });
    document.addEventListener("visibilitychange", function () { if (document.hidden) { cancelAnimationFrame(raf); } else { draw(); } });
  })();

  /* --- titolo a macchina da scrivere --- */
  (function tw() { var el = document.getElementById("heroType"); if (!el) return; var p = "See the close. Read the why.", cur = '<span class="type-cursor">&nbsp;</span>';
    if (reduce) { el.innerHTML = p + cur; return; } var i = 0; (function s() { el.innerHTML = p.slice(0, i) + cur; if (i < p.length) { var pause = p[i] === "." ? 260 : 0; i++; setTimeout(s, 55 + pause); } })(); })();

  /* --- striscione + lista LIVE: primo disegno dai mover della seduta (fallback);
         il poller live() sotto li sostituisce coi mover del momento appena arriva
         live.json, e li aggiorna a ogni refresh. --- */
  renderTicker(null);
  paintLiveMovers(null);

  /* --- stato del mercato USA, in ora di New York (gestisce da solo l'ora legale) --- */
  var forceClosed = /[?&]closed\b/.test(location.search);   // anteprima "mercato chiuso" feriale
  var forceWeekend = /[?&]weekend\b/.test(location.search);  // anteprima overlay weekend
  function usMarketState() {
    var parts = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", weekday: "short", hour: "2-digit", minute: "2-digit", hour12: false }).formatToParts(new Date());
    var get = function (t) { var f = parts.find(function (x) { return x.type === t; }); return f ? f.value : ""; };
    var wd = get("weekday"), hh = (+get("hour")) % 24, mm = +get("minute");
    var weekday = wd !== "Sat" && wd !== "Sun";
    var mins = hh * 60 + mm;
    return { open: weekday && mins >= 570 && mins < 960, weekday: weekday };   // 9:30–16:00 ET
  }
  function nextUsOpenLabel() {
    var now = new Date(new Date().toLocaleString("en-US", { timeZone: "America/New_York" }));
    var d = new Date(now); d.setHours(9, 30, 0, 0);
    while (d <= now || d.getDay() === 0 || d.getDay() === 6) { d.setDate(d.getDate() + 1); d.setHours(9, 30, 0, 0); }
    var days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"], mons = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    return days[d.getDay()] + " " + mons[d.getMonth()] + " " + d.getDate() + ", 9:30 AM ET";
  }
  // isWeekend pilota SOLO l'overlay a tutto schermo MERCATI CHIUSI (evento "grosso");
  // la chiusura feriale di sera usa invece il segno arancione dentro la vista LIVE.
  var isWeekend = (!usMarketState().weekday) || forceWeekend;

  /* --- viste: edition (editoriale) / live (indici + notizie) --- */
  function setView(v) {
    document.body.setAttribute("data-view", v);
    try { localStorage.setItem("view", v); } catch (e) {}
    document.querySelectorAll(".nav-link[data-go]").forEach(function (b) { b.classList.toggle("active", b.dataset.go === v); });
    if (v === "live" && isWeekend) openMcFull();
  }
  // Vista d'ingresso: a mercati APERTI si apre su LIVE (il dato corrente), a mercati
  // CHIUSI sull'edizione (il resoconto della seduta). La nav resta libera di passare
  // all'altra vista, e la scelta manuale vale per la sessione.
  var initialView = usMarketState().open ? "live" : "edition";
  document.body.setAttribute("data-view", initialView);

  function scrollToEl(sel) { var el = typeof sel === "string" ? document.querySelector(sel) : sel; if (!el) return false; var y = el.getBoundingClientRect().top + window.pageYOffset - HEADER_H - 14; window.scrollTo({ top: y < 0 ? 0 : y, behavior: "smooth" }); return true; }
  function goLive() { setView("live"); if (!isWeekend) scrollToEl("#liveStrip") || scrollToEl(".only-live"); }
  function goEdition() { closeMcFull(); setView("edition"); scrollToEl(".edition") || scrollToEl("#editionsContent"); }
  function openArchive() { closeMcFull(); setView("edition"); var t = document.getElementById("archiveToggle"); if (t && !document.querySelector(".archive-item")) { t.click(); setTimeout(function () { var n = document.getElementById("archiveToggle"); scrollToEl(n ? n.closest(".section-head") : "#editionsContent"); }, 90); } else { var n2 = document.getElementById("archiveToggle"); scrollToEl(n2 ? n2.closest(".section-head") : "#editionsContent"); } }

  document.querySelectorAll(".nav-link[data-go]").forEach(function (b) { b.addEventListener("click", function () { var g = b.dataset.go; if (g === "live") goLive(); else if (g === "edition") goEdition(); else if (g === "archive") openArchive(); }); });
  var gl = document.getElementById("goLiveBtn"); if (gl) gl.addEventListener("click", goLive);
  var ge = document.getElementById("goEditionBtn"); if (ge) ge.addEventListener("click", goEdition);
  document.querySelectorAll(".nav-link[data-go]").forEach(function (b) { b.classList.toggle("active", b.dataset.go === initialView); });

  /* --- banner weekend nell'hero --- */
  (function heroBanner() { var box = document.getElementById("marketClosed"); if (!box || !isWeekend) return;
    box.innerHTML = '<div class="mc-title"><span class="dot"></span>Markets closed</div><div class="mc-body">Wall Street is shut for the weekend. Tap <strong>LIVE</strong> for the countdown to the next opening bell; the edition below covers the last close.</div>'; box.hidden = false; })();

  /* --- overlay MERCATI CHIUSI + countdown --- */
  var EXCH = [
    { name: "Nasdaq-100", tz: "America/New_York", h: 9, m: 30 },
    { name: "S&P 500", tz: "America/New_York", h: 9, m: 30 },
    { name: "Dow Jones", tz: "America/New_York", h: 9, m: 30 },
    { name: "FTSE MIB", tz: "Europe/Rome", h: 9, m: 0 }
  ];
  function msToOpen(tz, h, m) { var now = new Date(new Date().toLocaleString("en-US", { timeZone: tz })); var d = new Date(now); d.setHours(h, m, 0, 0); while (d <= now || d.getDay() === 0 || d.getDay() === 6) { d.setDate(d.getDate() + 1); d.setHours(h, m, 0, 0); } return d - now; }
  function fmtDur(ms) { var s = Math.max(0, Math.floor(ms / 1000)); var d = Math.floor(s / 86400); s -= d * 86400; var hh = Math.floor(s / 3600); s -= hh * 3600; var mm = Math.floor(s / 60); var ss = s - mm * 60; var p = function (n) { return (n < 10 ? "0" : "") + n; }; return (d > 0 ? d + "d " : "") + p(hh) + ":" + p(mm) + ":" + p(ss); }
  var mcFull = document.getElementById("mcFull"), mcGrid = document.getElementById("mcGrid"), mcTimer = null;
  function renderMc() { if (!mcGrid) return; mcGrid.innerHTML = EXCH.map(function (e) { return '<div class="mc-ex"><div class="ex-name">' + e.name + '</div><div class="ex-time" data-tz="' + e.tz + '" data-h="' + e.h + '" data-m="' + e.m + '">--:--:--</div><div class="ex-sub">to open</div></div>'; }).join(""); tickMc(); }
  function tickMc() { if (!mcGrid) return; mcGrid.querySelectorAll(".ex-time").forEach(function (el) { el.textContent = fmtDur(msToOpen(el.dataset.tz, +el.dataset.h, +el.dataset.m)); }); }
  function openMcFull() { if (!mcFull) return; renderMc(); mcFull.classList.add("open"); if (mcTimer) clearInterval(mcTimer); mcTimer = setInterval(tickMc, 1000); }
  function closeMcFull() { if (!mcFull) return; mcFull.classList.remove("open"); if (mcTimer) { clearInterval(mcTimer); mcTimer = null; } }
  var mcClose = document.getElementById("mcCloseBtn"); if (mcClose) mcClose.addEventListener("click", function () { closeMcFull(); goEdition(); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeMcFull(); });

  /* --- striscia LIVE: segno stato mercato (verde aperto / arancione chiuso) +
         livelli indici (poll di live.json, stessa origine). Lo stato lo calcola il
         browser in ora di New York, cosi' e' esatto anche fra un aggiornamento e
         l'altro di live.json, e la scritta CLOSED compare come nel weekend. --- */
  (function live() {
    var strip = document.getElementById("liveStrip"); if (!strip) return;
    var latest = null;
    function statusHtml() {
      var s = usMarketState();
      var closed = !s.open || forceClosed || forceWeekend;
      if (!closed) return '<div class="live-status open"><span class="ls-dot"></span>U.S. markets open &middot; live</div>';
      var why = (!s.weekday || forceWeekend) ? "closed for the weekend" : "closed &middot; showing the last close";
      return '<div class="live-status closed"><span class="ls-dot"></span>U.S. markets ' + why + ' &middot; reopens ' + nextUsOpenLabel() + '</div>';
    }
    function paint() {
      var d = latest, items = (d && d.indices) || [];
      var when = ""; try { if (d && d.updated) when = new Date(d.updated).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); } catch (e) {}
      var idx = items.length
        ? '<div class="li-head"><span class="live-dot"></span>Index levels' + (when ? (' &middot; updated ' + when) : '') + '</div>' +
          items.map(function (i) { var cls = i.pct > 0 ? "up" : (i.pct < 0 ? "down" : "flat"), sign = i.pct > 0 ? "+" : ""; return '<div class="live-idx"><div class="li-name">' + i.label + '</div><div class="li-pct ' + cls + '">' + sign + Number(i.pct).toFixed(2) + '%</div></div>'; }).join("")
        : "";
      strip.innerHTML = statusHtml() + idx;
      strip.hidden = false;
      // Stessa fonte per striscione e lista LIVE: cambiano insieme a ogni refresh.
      renderTicker(latest);
      paintLiveMovers(latest);
    }
    function load() { fetch("live.json", { cache: "no-store" }).then(function (r) { return r.ok ? r.json() : null; }).then(function (d) { latest = d; paint(); }).catch(paint); }
    load();
    setInterval(load, 5 * 60 * 1000);   // ricarica i dati ogni 5 min (json minuscolo)
    setInterval(paint, 60 * 1000);      // ridisegna al minuto: cattura il passaggio aperto<->chiuso
  })();

  /* --- Subscribe --- */
  var modal = document.getElementById("subModal"), ob = document.getElementById("subscribeBtn"), cb = document.getElementById("subClose"), form = document.getElementById("subForm"), email = document.getElementById("subEmail"), msg = document.getElementById("subMsg");
  function om() { if (modal) { modal.classList.add("open"); setTimeout(function () { email && email.focus(); }, 60); } }
  function cm() { if (modal) modal.classList.remove("open"); }
  if (ob) ob.addEventListener("click", om); if (cb) cb.addEventListener("click", cm);
  if (modal) modal.addEventListener("click", function (e) { if (e.target === modal) cm(); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") cm(); });
  if (form) form.addEventListener("submit", function (e) { e.preventDefault(); var v = (email.value || "").trim(); if (!/.+@.+\..+/.test(v)) { msg.style.color = "var(--red-5,#f87171)"; msg.textContent = "Please enter a valid email address."; return; }
    window.open("https://maximedaverio.substack.com/subscribe?email=" + encodeURIComponent(v), "_blank", "noopener"); msg.style.color = "var(--green-5,#4ade80)"; msg.textContent = "Opening Substack to confirm — check the new tab."; email.value = ""; });
})();
