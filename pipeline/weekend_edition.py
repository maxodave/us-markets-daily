"""
L'edizione dei giorni SENZA seduta nuova: domenica, lunedi' e il giorno dopo una
festivita' di borsa.

Il problema che risolve. Il job gira tutte le notti, la borsa no. L'edizione di
sabato racconta la seduta di venerdi' ed e' la prima a farlo: e' giusta. Domenica
e lunedi' notte, pero', l'ultima seduta chiusa e' ancora quella di venerdi', e
fino a questa modifica le due edizioni ripubblicavano le STESSE percentuali,
gli stessi top gainer e gli stessi top loser — tre giorni di fila. Per un lettore
che apre il sito o la newsletter e' inutile e poco professionale.

La soluzione non e' saltare l'edizione (si perderebbero due uscite a settimana su
sette) ma cambiarne la natura: quando non c'e' una seduta nuova, l'edizione
diventa un RIASSUNTO DELLE NOTIZIE del giorno appena passato — sabato per
l'edizione di domenica, domenica per quella di lunedi' — piu' i pochi mercati che
nel fine settimana restano aperti davvero (fetch_weekend_signals.py). Zero
percentuali di seduta ripetute: e' la regola da cui nasce tutto questo file.

Due garanzie contro la ripetizione, non una:
  1. una FINESTRA TEMPORALE: si prendono solo le notizie pubblicate dopo il run
     precedente (24 ore, allargate a 48 se il sabato e' stato troppo tranquillo);
  2. una ESCLUSIONE ESPLICITA dei link gia' comparsi nel feed dell'edizione
     precedente. La finestra da sola non basta: i feed RSS ripropongono lo stesso
     articolo per giorni, e una data di pubblicazione mal formattata lo farebbe
     rientrare. Se un articolo e' gia' uscito ieri, qui non c'e'.

Nessuna IA in questo file: la selezione, i raggruppamenti e i paragrafi di
riserva sono deterministici, cosi' l'edizione del weekend esce identica a se
stessa anche senza API key. Il commento discorsivo — piu' bello da leggere — lo
aggiunge generate_commentary.py quando la chiave c'e', e la sua assenza non
lascia mai la pagina vuota.
"""
import json
import os
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from mover_reason import brand_tokens, is_trusted

SIGNALS_FILE = "weekend_signals.json"

# Finestra normale: dal run precedente a questo. 26 e non 24 per non perdere gli
# articoli sul bordo quando il job parte con qualche minuto di ritardo — i
# doppioni li toglie comunque l'esclusione dei link gia' pubblicati.
WINDOW_HOURS = 26
# Se il giorno e' stato tranquillo (agosto, festivita') si allarga invece di
# pubblicare mezza pagina vuota. Sempre con l'esclusione dei link gia' usati.
WIDE_WINDOW_HOURS = 48
MIN_ITEMS = 8
# Quante notizie mostrare per tema. Il feed completo resta piu' in basso nella
# pagina: questo e' il digest, e un digest che elenca tutto non e' un digest.
MAX_PER_SECTION = 6
MAX_TOTAL = 24
# Titoli citati nel paragrafo di riserva.
NARRATED_HEADLINES = 3

# I "segnali" della seduta di lunedi' non sono previsioni: sono i temi che le
# testate stesse indicano come appuntamenti gia' fissati (dati macro, banche
# centrali, trimestrali in arrivo). Un titolo che li nomina finisce nella lista
# "cosa guardare", con la sua fonte. Nessun giudizio, nessuna direzione.
WATCH_PATTERNS = (
    "week ahead", "the week ahead", "what to watch", "this week", "next week",
    "earnings preview", "earnings season", "on deck", "watch list",
    "federal reserve", "fomc", "the fed", "fed's", "fed’s", "fed chair",
    "rate cut", "rate hike", "interest rate", "rate decision",
    "inflation", "cpi ", "cpi,", "ppi ", "jobs report", "payrolls", "unemployment",
    "gdp", "central bank", "treasury yield", "bond yield", "tariff", "opec",
    "guidance", "outlook for", "quarterly results", "reports earnings",
    # Il fine settimana le testate scrivono gia' dell'apertura successiva: sono
    # i titoli piu' pertinenti in assoluto per un'edizione della domenica sera.
    "futures", "market open", "premarket", "pre-market", "open higher", "open lower",
    "prossima settimana", "settimana", "trimestrali", "inflazione", "tassi",
)

# Titoli che non aggiungono nulla a un digest: pura azione di prezzo, listicle,
# contenuti promozionali. Volutamente PIU' CORTA della lista in mover_reason.py:
# li' "week ahead" e' rumore (non spiega la seduta di ieri), qui e' esattamente
# cio' che serve.
NOISE_PATTERNS = (
    "stock quote", "stock price", "in real time", "advanced charts", "sec filings",
    "best stocks to", "should you buy", "is it time to buy", "better buy",
    "3 reasons", "prediction:", "here's how much", "if you'd invested",
    "motley fool", "zacks", "our top pick",
)

SECTION_LABELS = {
    "mercati": {"en": "Markets and macro", "it": "Mercati e macro"},
    "italia": {"en": "Italy", "it": "Italia"},
    "crypto": {"en": "Crypto", "it": "Crypto"},
    "tech": {"en": "Tech", "it": "Tech"},
    "scienza": {"en": "Science", "it": "Scienza"},
}
SECTION_ORDER = ("mercati", "crypto", "tech", "italia", "scienza")

DAYS_EN = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
DAYS_IT = ("lunedi'", "martedi'", "mercoledi'", "giovedi'", "venerdi'", "sabato", "domenica")


# ---------------------------------------------------------------------------
# Quando un'edizione e' un recap
# ---------------------------------------------------------------------------

def previous_edition(editions_dir: str, edition_date: str) -> dict | None:
    """L'edizione pubblicata piu' di recente PRIMA di questa."""
    try:
        names = sorted(
            n[: -len(".json")]
            for n in os.listdir(editions_dir)
            if n.endswith(".json")
        )
    except FileNotFoundError:
        return None
    earlier = [n for n in names if n < edition_date]
    if not earlier:
        return None
    try:
        with open(os.path.join(editions_dir, f"{earlier[-1]}.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def is_recap_edition(session_date: str, prev: dict | None) -> bool:
    """Vero quando la seduta da raccontare e' gia' stata raccontata.

    Si guarda il FATTO (la seduta e' la stessa dell'edizione precedente) e non il
    giorno della settimana. Cosi' la regola vale da sola anche il martedi' dopo un
    lunedi' di festa, e non va aggiornata a mano ogni anno con il calendario di
    borsa. Se per qualsiasi motivo i dati di mercato non si fossero aggiornati,
    l'effetto e' comunque quello giusto: si pubblica un riassunto di notizie
    invece di ripetere numeri gia' visti.
    """
    if not prev or not session_date:
        return False
    return prev.get("session_date") == session_date


# ---------------------------------------------------------------------------
# Selezione delle notizie
# ---------------------------------------------------------------------------

def parse_published(raw: str) -> datetime | None:
    """Data di un articolo, tollerante sul formato. Sempre in UTC.

    I feed usano RFC 822 ("Sat, 16 Aug 2026 14:02:00 +0000") ma non tutti: alcuni
    scrivono ISO 8601. Chi non e' interpretabile resta senza data e viene tenuto
    fuori dalla finestra: nel digest sta solo cio' di cui si sa QUANDO e' uscito.
    """
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        d = parsedate_to_datetime(raw)
    except Exception:
        try:
            d = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            return None
    if d is None:
        return None
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)


def previous_feed_links(prev: dict | None) -> set[str]:
    if not prev:
        return set()
    links = {i.get("link") for i in (prev.get("feed") or []) if i.get("link")}
    wr = prev.get("weekend_report") or {}
    for section in wr.get("sections") or []:
        for i in section.get("items") or []:
            if i.get("link"):
                links.add(i["link"])
    # Anche la lista "cosa guardare": e' fatta di anteprime e appuntamenti, cioe'
    # esattamente i titoli che una testata tiene in cima al feed per due giorni.
    # Senza questa riga l'edizione di lunedi' ripropone gli stessi tre titoli che
    # domenica erano gia' in calendario — la ripetizione, spostata di sezione.
    for w in wr.get("watchlist") or []:
        if w.get("link"):
            links.add(w["link"])
    return links


def is_noise(title: str) -> bool:
    low = (title or "").lower()
    return len(low) < 20 or any(p in low for p in NOISE_PATTERNS)


def watch_score(title: str) -> int:
    low = (title or "").lower()
    return sum(1 for p in WATCH_PATTERNS if p in low)


# Testate che pubblicano in italiano. Fuori dal tema "italia" i loro titoli
# vanno in coda: il sito e la newsletter hanno l'inglese come lingua originale, e
# un titolo in italiano in mezzo alla sezione "Crypto" di un digest inglese e'
# la prima cosa che un lettore nota — e non in bene. Restano comunque presenti:
# e' un ordinamento, non una censura, e con il pulsante IT hanno senso pieno.
ITALIAN_SOURCES = (
    "cryptonomist", "wired italia", "wall street italia", "finanzaonline",
    "ansa", "il sole 24 ore", "certificatejournal",
)


def is_italian_source(source: str) -> bool:
    low = (source or "").lower()
    return any(s in low for s in ITALIAN_SOURCES)


# I feed "mercati" delle grandi testate sono in realta' feed di ECONOMIA in senso
# largo: nello stesso flusso arrivano la mossa della Fed e il ritiro di un
# calciatore. Su una pagina che si chiama US Markets Daily il secondo non regge
# il primo posto. Un titolo che contiene uno di questi termini sale davanti agli
# altri dentro il proprio tema; gli altri non spariscono, scendono.
MARKET_TERMS = (
    "stock", "share", "market", "wall street", "s&p", "nasdaq", "dow jones",
    "index", "investor", "trading", "trader", "earnings", "revenue", "profit",
    "guidance", "fed", "federal reserve", "rate", "yield", "bond", "treasury",
    "inflation", "economy", "economic", "gdp", "jobs", "tariff", "dollar",
    "oil", "gold", "futures", "ipo", "merger", "acquisition", "buyback",
    "bank", "hedge fund", "valuation", "quarter", "billion", "bitcoin", "crypto",
)


# Confini di parola, e non una sottostringa qualsiasi: con il confronto "in" il
# termine "billion" fa match dentro "Billionaire", e il primo titolo del digest
# e' diventato il ritiro di un calciatore. La "s?" finale copre i plurali
# ("shares", "rates", "tariffs") che il confine di parola escluderebbe.
MARKET_TERMS_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(t) for t in MARKET_TERMS) + r")s?\b", re.I
)


def is_market_relevant(title: str) -> bool:
    return bool(MARKET_TERMS_RE.search(title or ""))


# Testate il cui mestiere principale sono i mercati. is_trusted() e' piu' largo
# di proposito (comprende Forbes, CNN, ANSA: fonti serie, ma generaliste), e in
# un digest di sei righe per tema la differenza si vede — senza questo livello,
# in cima a "Mercati e macro" finisce l'incasso di un film invece della Fed.
TIER1_SOURCES = (
    "reuters", "bloomberg", "wsj", "wall street journal", "financial times",
    "cnbc", "marketwatch", "barron", "economist", "associated press",
)


def is_tier1(source: str) -> bool:
    low = (source or "").lower()
    return any(s in low for s in TIER1_SOURCES)


def rank_key(item: dict) -> tuple:
    """Ordine di lettura dentro un tema.

    Nell'ordine: le testate di mercato, poi le altre riconosciute (le stesse che
    mover_reason.py accetta per citare una causa), i titoli che parlano davvero
    di mercati, chi scrive nella lingua del sito, chi ha un'immagine — il digest
    e' anche visivo — e infine il piu' recente. La rilevanza per "cosa guardare"
    NON entra qui: quella e' una lista a parte, e mescolarla altererebbe
    l'ordine del digest.
    """
    italian_ok = item.get("category") == "italia"
    source = item.get("source", "")
    return (
        0 if is_tier1(source) else 1,
        0 if is_trusted(source) else 1,
        # La lingua conta PRIMA della rilevanza per parola chiave: nella sezione
        # crypto, dove nessuna fonte e' di primo livello, ogni titolo contiene
        # "crypto" e il criterio lessicale non separa piu' nulla — il risultato
        # era una sezione inglese con quattro righe su sei in italiano.
        0 if (italian_ok or not is_italian_source(source)) else 1,
        0 if is_market_relevant(item.get("title", "")) else 1,
        0 if item.get("image") else 1,
        -(item.get("_dt").timestamp() if item.get("_dt") else 0),
    )


# Due titoli che condividono questa quota di parole significative raccontano la
# stessa storia. Serve perche' fetch_feed_news.py deduplica sul titolo esatto, e
# una testata che riscrive il proprio pezzo ("Tops $2 Billion On Record Third
# Weekend" / "Passes $2 Billion At Global Box Office") supera quel controllo e
# occupa due delle sei righe del tema.
NEAR_DUPLICATE_OVERLAP = 0.6
STOPWORDS = {
    "the", "a", "an", "of", "on", "in", "at", "to", "for", "and", "or", "as",
    "is", "are", "was", "were", "with", "from", "by", "its", "it", "after",
    "che", "di", "il", "la", "le", "un", "una", "per", "con", "del", "della",
}


def title_tokens(title: str) -> set[str]:
    words = re.findall(r"[a-z0-9$]+", (title or "").lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 2}


def drop_near_duplicates(items: list[dict]) -> list[dict]:
    kept: list[tuple[set[str], dict]] = []
    for it in items:
        toks = title_tokens(it.get("title", ""))
        if not toks:
            continue
        if any(
            len(toks & other) / min(len(toks), len(other)) >= NEAR_DUPLICATE_OVERLAP
            for other, _ in kept
        ):
            continue
        kept.append((toks, it))
    return [it for _, it in kept]


def select_items(feed_items: list[dict], now: datetime, exclude: set[str]) -> tuple[list[dict], int]:
    """Notizie del giorno appena passato, mai gia' pubblicate ieri.

    Restituisce (elenco, ore_di_finestra_usate): la finestra effettiva finisce
    nell'edizione, cosi' un lettore che si chiede "di che periodo si parla" trova
    la risposta scritta invece di doverla dedurre.
    """
    prepared = []
    for it in feed_items:
        link = it.get("link")
        if not link or link in exclude:
            continue
        title = it.get("title") or ""
        if is_noise(title):
            continue
        dt = parse_published(it.get("published", ""))
        if not dt:
            continue
        prepared.append({**it, "_dt": dt})

    for hours in (WINDOW_HOURS, WIDE_WINDOW_HOURS):
        cutoff = now - timedelta(hours=hours)
        chosen = [i for i in prepared if i["_dt"] >= cutoff]
        if len(chosen) >= MIN_ITEMS or hours == WIDE_WINDOW_HOURS:
            return chosen, hours
    return [], WIDE_WINDOW_HOURS


def build_sections(items: list[dict]) -> list[dict]:
    sections = []
    budget = MAX_TOTAL
    for key in SECTION_ORDER:
        group = sorted((i for i in items if i.get("category") == key), key=rank_key)
        # Dopo l'ordinamento, cosi' fra due riscritture della stessa storia
        # sopravvive quella meglio piazzata invece della prima incontrata.
        group = drop_near_duplicates(group)
        if not group:
            continue
        keep = group[: min(MAX_PER_SECTION, budget)]
        if not keep:
            break
        budget -= len(keep)
        sections.append({
            "key": key,
            "label": SECTION_LABELS.get(key, {"en": key, "it": key}),
            "n_available": len(group),
            "items": [
                {
                    "title": i.get("title", ""),
                    "source": i.get("source", ""),
                    # Il tema viaggia con la notizia e non solo sulla sezione:
                    # e' quello che colora il pallino della scheda sul sito
                    # (feedCard in app.js), che legge il campo dell'articolo.
                    "category": i.get("category", key),
                    "link": i.get("link", ""),
                    "image": i.get("image"),
                    "summary": i.get("summary", ""),
                    "published": i.get("published", ""),
                }
                for i in keep
            ],
        })
    return sections


def build_watchlist(items: list[dict]) -> list[dict]:
    """Titoli che nominano un appuntamento gia' in calendario.

    E' la parte "segnali" dell'edizione, e resta deliberatamente descrittiva:
    ogni voce e' un titolo vero con la sua testata, non una previsione. Solo
    fonti riconosciute: su una lista che il lettore leggera' come "cosa succede
    lunedi'" la provenienza conta piu' che altrove.
    """
    scored = [
        (watch_score(i.get("title", "")), i)
        for i in items
        if is_trusted(i.get("source", ""))
    ]
    scored = [(s, i) for s, i in scored if s > 0]
    scored.sort(key=lambda x: (-x[0], rank_key(x[1])))
    return [
        {"title": i.get("title", ""), "source": i.get("source", ""), "link": i.get("link", "")}
        for _, i in scored[:5]
    ]


# ---------------------------------------------------------------------------
# Segnali dal chiacchiericcio di nicchia: punteggio lessicale + ticker verificato
# ---------------------------------------------------------------------------
# L'idea (dagli appunti dell'utente in Perplexity_Projects/yahoo_rss_scraper.py):
# durante il weekend le notizie che potrebbero muovere un titolo lunedi' mattina
# non escono solo dalle testate di mercato — un pezzo tech su un'acquisizione, un
# post crypto su una violazione dati, una causa legale, spesso nominano una
# societa' quotata prima che qualunque "top mover" ufficiale ne parli. Questa
# sezione prova a intercettarle: punteggio lessicale REALE (parole come
# "surge"/"plunge"/"lawsuit", percentuali citate nel testo — nessuna IA, stessa
# logica dello script originale) applicato a TUTTE le notizie di nicchia gia'
# raccolte (crypto/tech/scienza, non solo mercati), con un ticker allegato SOLO
# quando il titolo nomina davvero una societa' dell'universo tracciato.
#
# La parte delicata e' quel "davvero": un punteggio alto senza una societa'
# verificata non e' un segnale, e' rumore. E la verifica dev'essere piu' severa
# di quella usata in mover_reason.py, perche' li' si controllano poche notizie
# GIA' associate a un ticker (quelle di fetch_news.py per quel titolo); qui si
# confrontano CENTINAIA di notizie generiche contro le ~518 societa' tracciate.
#
# La prima idea — richiedere la maiuscola esatta per un nome a una parola sola
# ("Target" societa' vs "target" obiettivo) — non regge: fallisce gia' su
# "NVIDIA'S $3 Billion Bet" (il titolo scrive il nome tutto maiuscolo, non
# "Nvidia"), e comunque non basterebbe. Scandagliando l'universo tracciato,
# decine di societa' hanno come nome una parola inglese comunissima che in un
# titolo compare capitalizzata semplicemente perche' inizia la frase: "Bank of
# England raises rates" capitalizza "Bank" (Bank of America, BAC) senza
# nominare la banca; lo stesso per "Healthcare" (GE HealthCare, GEHC),
# "Southern California wildfires" (Southern Company, SO), "News of the leak"
# (News Corp, NWS/NWSA), "Block" (Block Inc, XYZ). Nessuna euristica sulla
# maiuscola distingue questi casi.
#
# La verifica quindi e', nell'ordine: il ticker esplicito tra parentesi (sempre
# valido, e' inequivocabile); il nome a due parole, case-insensitive (due
# parole comuni insieme sono gia' rare abbastanza da non servire altro — stessa
# logica di mover_reason.headline_is_about); il nome a una parola sola,
# case-insensitive ma SOLO se quella parola non e' nell'elenco esplicito delle
# parole ambigue sotto. Per le societa' escluse questo canale semplicemente non
# scatta mai: restano comunque coperte se una notizia le cita col ticker o col
# nome completo. Preferire un falso negativo (nessun segnale) a un falso
# positivo (un ticker sbagliato) e' la stessa scelta che il resto del progetto
# fa sempre.
AMBIGUOUS_SINGLE_WORDS = frozenset({
    "bank", "news", "block", "healthcare", "southern", "church", "ball",
    "waters", "align", "industries", "packaging", "connectivity", "american",
    "aerospace", "everest", "flex", "target", "visa", "apple", "booking",
    "brown", "dover", "phillips", "semiconductor", "class", "on", "case",
    # Trovate scandagliando il feed reale (non nei test scritti a mano): "Dow"
    # e "Nasdaq" sono anche i nomi degli INDICI, citati in praticamente ogni
    # titolo di mercato ("Nasdaq sale dello 0,09%") senza nessun legame con Dow
    # Inc. (DOW, chimica) o Nasdaq Inc. (NDAQ, la borsa) — il falso positivo
    # sistematico che una scansione ampia ha fatto emergere.
    "dow", "nasdaq",
})

# Parole che segnalano un evento fuori dall'ordinario in un titolo. La lista di
# yahoo_rss_scraper.py (surge/plunge/crash...) e' pensata per notizie di
# mercato; qui il pool comprende anche tech/crypto/scienza, dove il catalizzatore
# tipico e' un'acquisizione, una causa, una violazione dati o un'approvazione
# regolatoria — eventi che davvero muovono un titolo lunedi' mattina.
STRONG_WORDS = (
    "surge", "soar", "plunge", "crash", "skyrocket", "tumble", "beats", "misses",
    "bombshell", "record", "rally", "slump", "spike", "collapse",
    "acquire", "acquisition", "merger", "lawsuit", "sues", "breach", "hack",
    "recall", "ban", "banned", "fine", "fined", "approval", "approved",
    "outage", "resigns", "fires", "layoffs", "bankruptcy",
)
PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s?%")
# Sotto questa soglia il punteggio e' rumore di base (il valore di partenza e'
# 3.0, e una singola parola forte da sola arriva solo a 4.2): serve almeno due
# parole forti nello stesso titolo ("recalls... tumble" = 5.4) o una parola
# forte con una percentuale vera perche' una notizia meriti di comparire.
NICHE_SIGNAL_THRESHOLD = 5.0
MAX_NICHE_SIGNALS = 6
# Sotto questa lunghezza una singola parola inglese comune (anche capitalizzata
# a inizio riga) rischia troppo il falso positivo per fare da solo il match.
MIN_SINGLE_TOKEN_LEN = 4


def score_headline(title: str, summary: str = "") -> tuple[float, float]:
    """Punteggio di intensita' lessicale (0-10) e percentuale eventualmente citata.

    Deterministico, nessuna IA: e' lo stesso schema di
    Perplexity_Projects/artifacts-2of2/yahoo_rss_scraper.py, verificato su dati
    reali (yahoo_rss_scored.csv) prima di questa modifica. Base 3.0, +1.2 per
    ogni parola dell'elenco trovata (si sommano: due parole forti pesano quanto
    una parola forte con una percentuale), + fino a 5 in base alla percentuale
    citata nel testo (piu' generosa quanto piu' e' grande il movimento
    menzionato), tutto tagliato a 10.
    """
    text = f"{title} {summary}".lower()
    score = 3.0
    for w in STRONG_WORDS:
        if w in text:
            score += 1.2
    m = PCT_RE.search(text)
    pct = float(m.group(1)) if m else 0.0
    if pct:
        score += min(pct / 5, 5)
    return round(min(score, 10.0), 1), pct


def match_company(title: str, company: dict) -> bool:
    """Vero solo se il titolo nomina DAVVERO questa societa'. Vedi il commento
    di sezione per il perche' delle tre soglie."""
    sym = company.get("symbol", "")
    if sym:
        esc = re.escape(sym)
        # \b prima del simbolo, non una sottostringa qualsiasi: senza, il
        # ticker a una lettera di Realty Income ("O") risultava nominato da
        # "...a potential IPO: FT" — "O:" e' dentro "IPO:", non un ticker.
        # Le parentesi di "(SYM)" da sole gia' bastano da confine (non sono
        # caratteri di parola), ma il \b esplicito non costa nulla e uniforma
        # i due controlli allo stesso trattamento.
        if re.search(r"\(" + esc + r"\)", title) or re.search(r"\b" + esc + r":", title):
            return True
    toks = brand_tokens(company.get("name", ""))
    if not toks:
        return False
    low = title.lower()
    if len(toks) >= 2:
        return all(t in low for t in toks)
    tok = toks[0]
    if len(tok) < MIN_SINGLE_TOKEN_LEN or tok in AMBIGUOUS_SINGLE_WORDS:
        return False
    return re.search(r"\b" + re.escape(tok) + r"\b", low) is not None


def find_niche_signals(items: list[dict], companies: list[dict]) -> list[dict]:
    """Le notizie di nicchia con punteggio piu' alto che nominano una societa'
    tracciata. Una per societa' (la piu' alta), ordinate per punteggio.

    "items" e' lo stesso pool gia' filtrato di select_items(): niente notizie
    gia' pubbliche ieri, niente titoli-rumore. Qui si aggiunge solo lo score e
    il collegamento al ticker — e' un arricchimento della stessa finestra
    temporale, non una ricerca a parte.
    """
    if not companies:
        return []
    best: dict[str, dict] = {}
    for it in items:
        title = it.get("title", "")
        score, pct = score_headline(title, it.get("summary", ""))
        if score < NICHE_SIGNAL_THRESHOLD:
            continue
        for c in companies:
            if not match_company(title, c):
                continue
            sym = c["symbol"]
            if sym in best and best[sym]["score"] >= score:
                continue
            best[sym] = {
                "symbol": sym,
                "name": c.get("name", ""),
                "score": score,
                "move_pct_mentioned": pct,
                "title": clean_title(title),
                "source": it.get("source", ""),
                "link": it.get("link", ""),
                "category": it.get("category", ""),
            }
    ranked = sorted(best.values(), key=lambda x: x["score"], reverse=True)
    return ranked[:MAX_NICHE_SIGNALS]


# ---------------------------------------------------------------------------
# Segnali di mercato del fine settimana
# ---------------------------------------------------------------------------

def load_signals(session_date: str, path: str = SIGNALS_FILE) -> dict | None:
    """weekend_signals.json, solo se riferito a QUESTA seduta.

    Il controllo sulla data e' lo stesso principio del commento manuale in
    build_edition.py: un file rimasto dal fine settimana scorso mostrerebbe
    variazioni "dalla chiusura di venerdi'" riferite a un altro venerdi'. Meglio
    nessun pannello che un pannello sbagliato.
    """
    try:
        with open(path, encoding="utf-8") as f:
            sig = json.load(f)
    except (FileNotFoundError, ValueError):
        return None
    if sig.get("reference_session") != session_date:
        return None
    return sig if sig.get("groups") else None


def flat_signals(signals: dict | None) -> list[dict]:
    if not signals:
        return []
    return [i for g in signals.get("groups", []) for i in g.get("instruments", [])]


def noteworthy_signals(signals: dict | None) -> list[dict]:
    """I movimenti abbastanza ampi da essere citati nel testo, i piu' larghi prima."""
    if not signals:
        return []
    threshold = signals.get("noteworthy_pct", 1.0)
    rows = [i for i in flat_signals(signals) if abs(i.get("pct_change", 0)) >= threshold]
    rows.sort(key=lambda i: abs(i["pct_change"]), reverse=True)
    return rows


# ---------------------------------------------------------------------------
# Testo di riserva (deterministico)
# ---------------------------------------------------------------------------

def fmt_pct(v: float, lang: str) -> str:
    s = f"{'+' if v > 0 else ''}{v:.2f}%"
    return s.replace(".", ",") if lang == "it" else s


def day_name(date_str: str, lang: str) -> str:
    try:
        w = datetime.strptime(date_str, "%Y-%m-%d").weekday()
    except Exception:
        return ""
    return (DAYS_EN if lang == "en" else DAYS_IT)[w]


def clean_title(title: str) -> str:
    """Titolo senza il suffisso " - Testata" e senza spazi doppi."""
    t = re.sub(r"\s+", " ", (title or "")).strip()
    return t.rsplit(" - ", 1)[0].strip() if " - " in t else t


def build_paragraphs(report: dict, session_date_label: str, lang: str) -> list[str]:
    """Resoconto in prosa del weekend, dagli stessi dati per entrambe le lingue.

    Stesso principio di build_edition.build_paragraphs: i numeri si calcolano una
    volta, il testo si scrive due volte. Non e' una traduzione automatica.
    """
    covers = report["covers_date_en"] if lang == "en" else report["covers_date_it"]
    dname = day_name(report["covers_date"], lang)
    n_items = report["n_items"]
    n_digest = report["n_digest"]
    n_sources = report["n_sources"]

    if lang == "en":
        p1 = (
            f"US markets were closed on {dname}, {covers}, so there is no new session to report: "
            f"the last one, {session_date_label}, was covered in the previous edition and its "
            f"numbers are not repeated here. This edition reads instead the {n_items} stories "
            f"published since then by {n_sources} outlets we track, and brings forward the "
            f"{n_digest} that matter most."
        )
    else:
        p1 = (
            f"I mercati americani erano chiusi {dname} {covers}: non c'e' una seduta nuova da "
            f"raccontare — l'ultima, {session_date_label}, e' gia' stata coperta dall'edizione "
            f"precedente e i suoi numeri qui non vengono ripetuti. Questa edizione legge invece "
            f"le {n_items} notizie uscite da allora su {n_sources} testate seguite, e porta in "
            f"primo piano le {n_digest} piu' rilevanti."
        )

    parts = [p1]

    lead = report.get("lead_headlines") or []
    if lead:
        rendered = "; ".join(
            (f"{h['source']} reports: “{h['title']}”" if lang == "en"
             else f"{h['source']} riporta: «{h['title']}»")
            for h in lead[:NARRATED_HEADLINES]
        )
        parts.append(
            f"Leading the weekend coverage: {rendered}." if lang == "en"
            else f"In evidenza nel fine settimana: {rendered}."
        )

    counts = [
        (s["label"][lang], s["n_available"])
        for s in report.get("sections", [])
    ]
    if counts:
        listed = ", ".join(f"{lab} ({n})" for lab, n in counts)
        parts.append(
            f"By theme: {listed}." if lang == "en" else f"Per tema: {listed}."
        )

    moves = report.get("signals_noteworthy") or []
    if moves:
        rendered = "; ".join(
            f"{(m['name_en'] if lang == 'en' else m['name_it'])} {fmt_pct(m['pct_change'], lang)}"
            for m in moves[:4]
        )
        if lang == "en":
            parts.append(
                f"What did trade while the exchanges were shut, measured from Friday's US close: "
                f"{rendered}. These are the only market moves in this edition — they are quotes, "
                f"not forecasts."
            )
        else:
            parts.append(
                f"Cosa ha scambiato a borse chiuse, misurato dalla chiusura americana di venerdi': "
                f"{rendered}. Sono gli unici movimenti di mercato di questa edizione: quotazioni, "
                f"non previsioni."
            )
    elif report.get("signals"):
        if lang == "en":
            parts.append(
                "The markets that stay open over the weekend — crypto, futures, currencies — "
                "moved less than a percent from Friday's US close: a quiet weekend, on the numbers."
            )
        else:
            parts.append(
                "I mercati che restano aperti nel fine settimana — crypto, futures, valute — si "
                "sono mossi meno dell'un per cento dalla chiusura americana di venerdi': sui "
                "numeri, un weekend tranquillo."
            )

    # Nessun paragrafo sugli appuntamenti: la lista "cosa guardare" ha una
    # colonna sua sul sito e una sezione sua nel post, entrambe con i link. Un
    # paragrafo che ripete gli stessi tre titoli a fianco della lista che li
    # contiene e' ripetizione dentro la stessa pagina — la versione in piccolo
    # del problema che questa edizione risolve.

    signals = report.get("niche_signals") or []
    if signals:
        rendered = "; ".join(
            f"{s['name']} ({s['symbol']}, {s['score']}/10) — {s['source']}: “{s['title']}”"
            if lang == "en" else
            f"{s['name']} ({s['symbol']}, {s['score']}/10) — {s['source']}: «{s['title']}»"
            for s in signals[:3]
        )
        if lang == "en":
            parts.append(
                f"Named in this weekend's coverage, scored only for how intensely the outlets "
                f"themselves wrote about it — not a forecast of Monday's move: {rendered}."
            )
        else:
            parts.append(
                f"Nominate nella copertura del weekend, con un punteggio che misura solo quanto "
                f"intensamente ne hanno scritto le testate — non una previsione per lunedi': "
                f"{rendered}."
            )
    return parts


def build_headline(report: dict, lang: str) -> str:
    dname = day_name(report["covers_date"], lang)
    moves = report.get("signals_noteworthy") or []
    if lang == "en":
        base = f"Markets closed: {dname}'s news in brief"
        if moves:
            m = moves[0]
            base += f", with {m['name_en']} {fmt_pct(m['pct_change'], 'en')} since Friday's close"
        return base
    base = f"Mercati chiusi: le notizie di {dname} in sintesi"
    if moves:
        m = moves[0]
        base += f", con {m['name_it']} {fmt_pct(m['pct_change'], 'it')} dalla chiusura di venerdi'"
    return base


# ---------------------------------------------------------------------------
# Assemblaggio
# ---------------------------------------------------------------------------

def build_report(
    edition_date: str,
    session_date: str,
    session_date_label: dict,
    feed_items: list[dict],
    prev: dict | None,
    italian_date,
    english_date,
    companies: list[dict] | None = None,
    now: datetime | None = None,
) -> dict:
    """Il blocco "weekend_report" dell'edizione.

    italian_date/english_date arrivano da build_edition.py invece di essere
    riscritte qui: le date del sito devono essere formattate in un solo posto,
    altrimenti prima o poi il weekend scrive "16 August" e il resto "August 16".
    """
    now = now or datetime.now(timezone.utc)
    covers_date = (datetime.strptime(edition_date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")

    already_published = previous_feed_links(prev)
    items, window_hours = select_items(feed_items, now, already_published)

    # "Cosa guardare" si sceglie PRIMA del digest, e i suoi titoli escono dal
    # digest: sono le stesse notizie, e vederle una volta tra le notizie del
    # giorno e una seconda tra gli appuntamenti fa sembrare il post piu' corto di
    # quello che e'. Ogni storia compare una volta sola, nel posto in cui vale di
    # piu' — e per un'edizione della domenica sera vale di piu' in fondo.
    watchlist = build_watchlist(items)
    if not watchlist and already_published:
        # Rete di sicurezza per il lunedi', l'edizione che di questa lista ha piu'
        # bisogno: se un fine settimana tranquillo non ha prodotto una sola
        # anteprima nuova, si riammettono quelle gia' viste ieri invece di
        # lasciare vuota la sezione. Una "week ahead" del Financial Times letta
        # due volte resta utile — non e' il caso delle percentuali di venerdi',
        # che raccontano il passato e per questo non tornano mai.
        wider, _ = select_items(feed_items, now, set())
        watchlist = build_watchlist(wider)
    watch_links = {w["link"] for w in watchlist if w.get("link")}
    sections = build_sections([i for i in items if i.get("link") not in watch_links])
    shown = [i for s in sections for i in s["items"]]

    # Cio' che resta della finestra, gia' senza i titoli finiti nel digest: e' il
    # feed che la pagina mostra piu' in basso. Sottrarre il digest e' il motivo
    # per cui questa lista si calcola qui e non in build_edition.py — altrimenti
    # il lettore troverebbe le stesse notizie due volte nella stessa pagina.
    in_digest = {i["link"] for i in shown} | watch_links
    leftover = [
        {k: i[k] for k in ("title", "source", "category", "published", "link", "summary", "image") if k in i}
        for i in sorted(items, key=rank_key)
        if i.get("link") not in in_digest
    ]

    lead = [
        {"title": clean_title(i["title"]), "source": i["source"], "link": i["link"]}
        for i in shown
        if is_trusted(i["source"])
    ][:NARRATED_HEADLINES]

    signals = load_signals(session_date)
    # Sull'INTERA finestra, non solo su "shown": una notizia che nomina una
    # societa' resta un segnale anche se non e' fra le sei mostrate nel digest
    # del suo tema (il digest e' un taglio editoriale, non un filtro di rilevanza
    # per QUESTA lente diversa). Esclusa solo la lista "in calendario": quelle
    # sono gia' presentate come appuntamenti, non hanno bisogno di un punteggio.
    niche_signals = find_niche_signals(
        [i for i in items if i.get("link") not in watch_links], companies or []
    )

    report = {
        "kind": "weekend_recap",
        "covers_date": covers_date,
        "covers_date_it": italian_date(covers_date),
        "covers_date_en": english_date(covers_date),
        "window_hours": window_hours,
        # n_items = tutto cio' che e' uscito nella finestra; n_digest = quanto ne
        # mostra il digest. Devono restare due numeri distinti: dire "18 notizie"
        # e poi elencare per tema 62+17+11 e' il tipo di incoerenza che un lettore
        # nota subito e che toglie credibilita' al resto della pagina.
        "n_items": len(items),
        "n_digest": len(shown),
        "n_sources": len({i.get("source") for i in items if i.get("source")}),
        "sections": sections,
        "feed_leftover": leftover,
        "lead_headlines": lead,
        "watchlist": watchlist,
        "niche_signals": niche_signals,
        "signals": signals,
        "signals_noteworthy": noteworthy_signals(signals),
    }

    report["paragraphs"] = {
        "en": build_paragraphs(report, session_date_label["en"], "en"),
        "it": build_paragraphs(report, session_date_label["it"], "it"),
    }
    report["headline"] = {
        "en": build_headline(report, "en"),
        "it": build_headline(report, "it"),
    }
    return report
