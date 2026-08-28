"""
Crea l'edizione del giorno in editions/YYYY-MM-DD.json.

Convenzione date (come una vera newsletter di mercato):
  - la data dell'EDIZIONE e' il giorno di pubblicazione (oggi);
  - il contenuto riguarda l'ULTIMA SEDUTA chiusa (in genere ieri), cioe'
    data.json -> generated_at.
Esempio: l'edizione del 5 agosto racconta la seduta del 4 agosto.

Il resoconto e' generato in modo DETERMINISTICO dai dati (nessuna IA), sia in
inglese sia in italiano: i NUMERI si calcolano una volta sola
(build_stats_and_movers), il TESTO si scrive due volte con gli stessi valori
(build_paragraphs, con lang="en"/"it"). Non e' una traduzione — e' lo stesso
calcolo raccontato in due lingue — perche' un errore di traduzione su un dato
di fatto (una percentuale, un conteggio) non e' un rischio accettabile su un
sito che pubblica di notte senza revisione.

Multi-indice: ogni titolo in data.json porta un campo "indices" (fetch_data.py)
con gli indici di cui fa parte (sp500/dow/nasdaq100). Il resoconto si calcola
per ciascun indice (filtro su "indices") PIU' una vista "combined" — che e'
semplicemente lo stesso calcolo senza filtro, sull'intero universo deduplicato:
nessuna logica di fusione in piu', perche' l'universo e' gia' deduplicato alla
fonte (fetch_data.py).

Compatibilita': il campo "auto_report" di livello radice resta quello di sempre
(solo S&P 500, solo italiano) — build_publish.py e build_dashboard.py continuano
a leggerlo senza modifiche. La nuova struttura multi-indice/bilingue vive in un
campo AGGIUNTIVO, "auto_report_by_index".

Se esiste un commento scritto a mano (o da generate_commentary.py) per la stessa
seduta in market_summary.json, viene usato come paragrafo di apertura in aggiunta
al resoconto automatico.

DUE TIPI DI EDIZIONE. Il campo "edition_kind" dice quale:
  - "session"       — c'e' una seduta nuova da raccontare (da martedi' a sabato);
  - "weekend_recap" — non c'e' (domenica, lunedi', giorno dopo una festivita').
Nel secondo caso l'edizione NON ripete le percentuali e i mover della seduta gia'
pubblicata: diventa un riassunto delle notizie del giorno appena passato piu' i
mercati che nel fine settimana restano aperti. Tutta la logica sta in
weekend_edition.py; qui c'e' solo il bivio. Il blocco "auto_report" viene scritto
comunque, perche' e' l'archivio dei dati della seduta e diverse parti del progetto
lo leggono, ma nessuna vista del recap lo mostra.

Le edizioni non vengono mai sovrascritte a meno di --force: l'archivio e' la
cronologia del sito.

Uso:
    python3 build_edition.py            # crea l'edizione di oggi se manca
    python3 build_edition.py --force    # rigenera l'edizione di oggi
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import weekend_edition
from mover_reason import pick_reason

# Il fuso della borsa. Una seduta ha una data sola solo se la si guarda da New
# York: in UTC la chiusura estiva cade alle 20:00 e quella invernale alle 21:00,
# e un job che gira dopo la mezzanotte italiana vede gia' il giorno dopo.
NY_TZ = ZoneInfo("America/New_York")

DATA_FILE = "data.json"
FEED_FILE = "feed_news.json"
MANUAL_SUMMARY_FILE = "market_summary.json"
# Commento discorsivo delle edizioni senza seduta nuova. File separato da
# market_summary.json e indicizzato per DATA DELL'EDIZIONE, non della seduta:
# domenica e lunedi' condividono la stessa seduta di riferimento, quindi una
# chiave sulla seduta farebbe leggere a lunedi' il commento scritto per domenica.
WEEKEND_SUMMARY_FILE = "weekend_summary.json"
# Riassunto discorsivo delle notizie top della sezione "Mercati" (la riga
# laterale colorata dell'edizione). Scritto da generate_commentary.py con l'API
# Claude e indicizzato per DATA DELL'EDIZIONE (come il weekend: le notizie di
# sabato non sono quelle di domenica). Se il file manca o e' di un altro giorno,
# l'edizione ricade sulla lista dei titoli top, sempre presente.
MARKETS_BRIEF_FILE = "markets_brief.json"
# Quotazioni LIVE dell'ultimo run della giornata: da qui si ricava lo SNAPSHOT di
# chiusura della lista LIVE, congelato nell'edizione. Vedi load_live_close_movers().
LIVE_FILE = "live.json"
# Quante notizie "Mercati" tenere per la riga laterale (e come materiale per la
# prosa). Poche e in vista: la lista completa resta nel feed sotto.
TOP_MARKETS_NEWS = 5
EDITIONS_DIR = "editions"

MESI_IT = {
    1: "gennaio", 2: "febbraio", 3: "marzo", 4: "aprile", 5: "maggio", 6: "giugno",
    7: "luglio", 8: "agosto", 9: "settembre", 10: "ottobre", 11: "novembre", 12: "dicembre",
}
MONTHS_EN = {
    1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June",
    7: "July", 8: "August", 9: "September", 10: "October", 11: "November", 12: "December",
}

INDEX_KEYS = ("sp500", "dow", "nasdaq100", "ftsemib", "combined")
# "combined" e' l'unione deduplicata di questi tre soli (Wall Street): il FTSE MIB
# ha valuta e orari di borsa diversi, e resta un tab a se', mai sommato agli USA.
# Vedi il bivio su questa costante dentro il ciclo di main().
US_INDEX_KEYS = ("sp500", "dow", "nasdaq100")
INDEX_LABELS = {
    "sp500": {"it": "l'S&P 500", "en": "the S&P 500"},
    "dow": {"it": "il Dow Jones", "en": "the Dow Jones"},
    "nasdaq100": {"it": "il Nasdaq-100", "en": "the Nasdaq-100"},
    "ftsemib": {"it": "il FTSE MIB", "en": "the FTSE MIB"},
    "combined": {"it": "l'insieme dei tre indici USA", "en": "the combined three U.S. indices"},
}

# Notizie da mostrare nel feed visuale dell'edizione
FEED_CATEGORIES = ("mercati", "italia", "crypto", "tech", "scienza")
MAX_FEED_ITEMS = 40
# 10 per lato: l'edizione mostra i 10 top gainer e i 10 top loser della seduta, e
# il blocco "notizie dietro i mover" ne deriva fino a 20 schede (una per titolo).
# fetch_news.py ne interroga gia' 12 per lato (MOVERS_ONLY_N), quindi c'e' margine.
TOP_MOVERS = 10
# Quanti mover citare nel paragrafo che riassume le notizie della seduta. Pochi e
# spiegati vale piu' di otto elencati: la lista completa e' comunque nelle due
# colonne accanto al testo.
NARRATED_MOVERS = 3
# Società minime perché un settore entri nella classifica migliori/peggiori.
# Vedi build_auto_report(): serve a non far vincere un settore da una società sola.
MIN_SECTOR_SAMPLE = 3


def italian_date(date_str: str) -> str:
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return f"{d.day} {MESI_IT[d.month]} {d.year}"
    except Exception:
        return date_str or "n/d"


def english_date(date_str: str) -> str:
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return f"{MONTHS_EN[d.month]} {d.day}, {d.year}"
    except Exception:
        return date_str or "n/a"


def fmt_pct(v: float, lang: str = "it") -> str:
    s = f"{'+' if v > 0 else ''}{v:.2f}%"
    return s.replace(".", ",") if lang == "it" else s


def _slim(items: list[dict]) -> list[dict]:
    return [{"title": n["title"], "source": n["source"], "link": n["link"]} for n in items]


def movers_entry(c: dict) -> dict:
    # Recenti e storiche restano SEPARATE: per spiegare la seduta di ieri vale solo
    # una notizia recente. Mescolarle porta ad attribuzioni contraddittorie (un
    # titolo salito del 10% "spiegato" da una notizia di giorni prima che parlava
    # di un calo). Lo storico serve al contesto, non come causa.
    #
    # FTSE MIB fa eccezione DI PROPOSITO: select_movers() di fetch_news.py non lo
    # interroga mai (elenca solo sp500/dow/nasdaq100), quindi qui non ci sarebbe
    # comunque nulla da leggere — ma alcune societa' italiane grandi (Ferrari,
    # Stellantis...) potrebbero avere notizie in inglese per altri motivi. Il
    # controllo esplicito rende la scelta "solo prezzo, niente motivo" garantita
    # e non un caso fortunato.
    is_ftsemib = "ftsemib" in (c.get("indices") or [])
    return {
        "symbol": c["symbol"],
        "name": c["name"],
        "sector": c["sector"],
        "pct_change": c["pct_change"],
        "last_close": c["last_close"],
        "indices": c.get("indices") or [],
        "reason": None if is_ftsemib else pick_reason(c, news_key="news_recent"),
        "news": [] if is_ftsemib else _slim((c.get("news_recent") or [])[:6]),
        "news_historical": [] if is_ftsemib else _slim((c.get("news_historical") or [])[:3]),
    }


def build_stats_and_movers(companies: list[dict]) -> tuple[dict, list[dict], list[dict]]:
    """Calcola stats/gainers/losers UNA VOLTA: nessuna lingua qui, solo numeri."""
    ups = [c for c in companies if c["pct_change"] > 0]
    downs = [c for c in companies if c["pct_change"] < 0]
    flat = [c for c in companies if c["pct_change"] == 0]
    ordered = sorted(companies, key=lambda c: c["pct_change"], reverse=True)
    gainers = [movers_entry(c) for c in ordered[:TOP_MOVERS]]
    losers = [movers_entry(c) for c in reversed(ordered[-TOP_MOVERS:])]

    avg = sum(c["pct_change"] for c in companies) / len(companies) if companies else 0.0

    by_sector: dict[str, list[float]] = {}
    for c in companies:
        by_sector.setdefault(c.get("sector") or "N/D", []).append(c["pct_change"])
    # Un settore con una o due societa' non ha una "variazione media" che significhi
    # qualcosa: nella vista combinata i titoli esclusivamente Nasdaq-100 portano
    # nomi di settore ICB che l'S&P 500 non usa, e ne e' bastato uno (SPCX,
    # "Telecommunications", n=1) per apparire come settore piu' forte della seduta
    # a +6,14%. Sotto la soglia il settore resta nei dati, ma fuori dalla classifica.
    ranked = sorted(
        (
            (s, sum(v) / len(v))
            for s, v in by_sector.items()
            if len(v) >= MIN_SECTOR_SAMPLE
        ),
        key=lambda x: x[1],
        reverse=True,
    )
    best_sectors = ranked[:3]
    worst_sectors = list(reversed(ranked[-3:]))

    stats = {
        "n_up": len(ups),
        "n_down": len(downs),
        "n_flat": len(flat),
        "n_total": len(companies),
        "avg_pct": round(avg, 2),
        "best_sectors": [{"sector": s, "avg_pct": round(v, 2)} for s, v in best_sectors],
        "worst_sectors": [{"sector": s, "avg_pct": round(v, 2)} for s, v in worst_sectors],
    }
    return stats, gainers, losers


def narrate_mover(m: dict, lang: str) -> str:
    """Un mover in una frase: nome, ticker, variazione e, se c'e', la notizia che
    la spiega con la testata. Senza notizia si ferma alla percentuale: meglio dire
    solo il fatto che riempire con una motivazione che non risulta."""
    base = f"{m['name']} ({m['symbol']}, {fmt_pct(m['pct_change'], lang)})"
    r = m.get("reason")
    if not r:
        return base
    if lang == "it":
        return f"{base}, dove {r['source']} riporta: «{r['title']}»"
    return f"{base}, where {r['source']} reports: “{r['title']}”"


def build_movers_paragraph(gainers: list[dict], losers: list[dict], lang: str) -> str:
    up = "; ".join(narrate_mover(m, lang) for m in gainers[:NARRATED_MOVERS])
    down = "; ".join(narrate_mover(m, lang) for m in losers[:NARRATED_MOVERS])
    parts = []
    if lang == "it":
        if up:
            parts.append(f"In cima alla seduta: {up}.")
        if down:
            parts.append(f"In fondo: {down}.")
    else:
        if up:
            parts.append(f"Leading the session: {up}.")
        if down:
            parts.append(f"At the bottom: {down}.")
    return " ".join(parts)


def build_paragraphs(
    index_key: str, stats: dict, gainers: list[dict], losers: list[dict], session_date: str, lang: str
) -> list[str]:
    """Resoconto in prosa per UN indice e UNA lingua, dai numeri gia' calcolati.

    Per index_key="sp500", lang="it" questo produce ESATTAMENTE il testo che il
    codice generava prima dell'introduzione multi-indice (verificato con un
    confronto byte a byte): e' il campo "auto_report" di livello radice.
    """
    label = INDEX_LABELS[index_key][lang]
    ups, downs, flat, total = stats["n_up"], stats["n_down"], stats["n_flat"], stats["n_total"]
    avg = fmt_pct(stats["avg_pct"], lang)

    if lang == "it":
        p1 = (
            f"Nella seduta del {italian_date(session_date)} {label} ha chiuso con "
            f"{ups} societa' in rialzo, {downs} in ribasso"
            + (f" e {flat} invariate" if flat else "")
            + f", su {total} titoli monitorati. La variazione media dell'indice "
            f"e' stata di {avg}."
        )
        best = "; ".join(f"{s['sector']} ({fmt_pct(s['avg_pct'], 'it')})" for s in stats["best_sectors"])
        worst = "; ".join(f"{s['sector']} ({fmt_pct(s['avg_pct'], 'it')})" for s in stats["worst_sectors"])
        p2 = f"Settori con la variazione media migliore: {best}. Settori piu' debolli: {worst}."
    else:
        p1 = (
            f"In the {english_date(session_date)} session {label} closed with "
            f"{ups} stocks higher, {downs} lower"
            + (f" and {flat} unchanged" if flat else "")
            + f", out of {total} tracked. The average move was {avg}."
        )
        best = "; ".join(f"{s['sector']} ({fmt_pct(s['avg_pct'], 'en')})" for s in stats["best_sectors"])
        worst = "; ".join(f"{s['sector']} ({fmt_pct(s['avg_pct'], 'en')})" for s in stats["worst_sectors"])
        p2 = f"Best-performing sectors by average move: {best}. Weakest: {worst}."

    paragraphs = [p1, p2]
    movers_para = build_movers_paragraph(gainers, losers, lang)
    if movers_para:
        paragraphs.append(movers_para)
    return paragraphs


def load_feed_raw() -> list[dict]:
    """Tutte le notizie del feed, senza tagli.

    Separata da load_feed_items() perche' l'edizione del fine settimana deve
    poter filtrare sull'orario di pubblicazione: partire dai 40 gia' selezionati
    per immagine escluderebbe titoli recenti solo perche' senza foto.
    """
    try:
        with open(FEED_FILE) as f:
            feed = json.load(f)
    except FileNotFoundError:
        return []
    return [i for i in feed.get("items", []) if i.get("category") in FEED_CATEGORIES]


def load_feed_items(items: list[dict] | None = None) -> list[dict]:
    """I MAX_FEED_ITEMS articoli del feed, scelti a ROUND-ROBIN per testata.

    Prima si prendeva "prima quelli con immagine, poi il resto, taglia a 40": con
    tante testate i 40 slot si riempivano coi soli articoli con foto delle fonti
    piu' prolifiche, e chi non ha immagine (Reuters/Barron's via Google News) o
    pubblica meno non entrava MAI. Qui invece ogni testata contribuisce a turno il
    suo articolo piu' recente, poi il secondo, ecc.: cosi' TUTTE le fonti scelte
    compaiono, con l'immagine preferita dentro ciascuna testata. La lista finale
    resta ordinata per data (gli articoli in ingresso lo sono gia')."""
    items = load_feed_raw() if items is None else items
    for rank, it in enumerate(items):
        it["_rank"] = rank  # posizione cronologica d'origine (0 = piu' recente)

    by_source: dict[str, list[dict]] = {}
    for it in items:
        by_source.setdefault(it.get("source", ""), []).append(it)
    # dentro ogni testata: prima gli articoli con immagine, ordine cronologico
    # preservato (sort stabile su una lista gia' ordinata per data).
    for group in by_source.values():
        group.sort(key=lambda i: 0 if i.get("image") else 1)
    # testate ordinate per quanto e' fresco il loro articolo migliore
    order = sorted(by_source.values(), key=lambda g: g[0]["_rank"])

    selected: list[dict] = []
    depth = 0
    while len(selected) < MAX_FEED_ITEMS:
        advanced = False
        for group in order:
            if depth < len(group):
                selected.append(group[depth])
                advanced = True
                if len(selected) >= MAX_FEED_ITEMS:
                    break
        if not advanced:
            break
        depth += 1

    selected.sort(key=lambda i: i["_rank"])  # visualizzazione: piu' recenti in alto
    for it in selected:
        it.pop("_rank", None)
    return selected


def feed_fetched_at() -> datetime | None:
    """Quando il feed e' stato raccolto, in UTC.

    E' l'ancora giusta per la finestra "ultime 24 ore" dell'edizione del fine
    settimana: se un run parte in ritardo, o viene rilanciato a mano il giorno
    dopo, contare dall'ora di ADESSO sposterebbe la finestra su notizie che il
    feed non contiene nemmeno. Se il campo manca si torna all'ora corrente.
    """
    try:
        with open(FEED_FILE) as f:
            raw = json.load(f).get("fetched_at")
        return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def load_manual_summary(session_date: str) -> dict | None:
    try:
        with open(MANUAL_SUMMARY_FILE) as f:
            ms = json.load(f)
    except FileNotFoundError:
        return None
    if ms.get("date") != session_date:
        return None  # commento scritto per un'altra seduta: non riusarlo
    return ms


def load_weekend_summary(edition_date: str) -> dict | None:
    """Commento discorsivo dell'edizione senza seduta, se scritto per QUESTA.

    Il confronto e' sulla data dell'EDIZIONE: domenica e lunedi' hanno la stessa
    seduta di riferimento, quindi una chiave sulla seduta farebbe ricomparire di
    lunedi' il testo di domenica — la ripetizione che questa funzionalita' esiste
    per eliminare.
    """
    try:
        with open(WEEKEND_SUMMARY_FILE, encoding="utf-8") as f:
            ws = json.load(f)
    except (FileNotFoundError, ValueError):
        return None
    return ws if ws.get("edition_date") == edition_date else None


def session_of_capture(captured_at: str) -> str | None:
    """La seduta a cui appartiene una foto, dal suo istante di scrittura.

    Una foto scritta DOPO la campana e PRIMA dell'apertura successiva contiene i
    valori di chiusura di quella seduta: dopo la mezzanotte di New York la data
    del calendario cambia, la seduta fotografata no. Serve per etichettare le
    foto vecchie che non portano con se' la propria seduta.
    """
    try:
        ny = (datetime.strptime(captured_at, "%Y-%m-%dT%H:%M:%SZ")
              .replace(tzinfo=timezone.utc).astimezone(NY_TZ))
    except (TypeError, ValueError):
        return None
    # Prima della campana appartiene alla seduta precedente; dopo, a quella di oggi.
    d = ny.date() if ny.hour * 60 + ny.minute >= 16 * 60 else ny.date() - timedelta(days=1)
    while d.weekday() >= 5:            # sabato/domenica: la seduta e' il venerdi'
        d -= timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def capture_window(session_date: str) -> tuple[datetime, datetime] | None:
    """La finestra, in ora di New York, in cui live.json contiene ancora la
    CHIUSURA di `session_date`: dalla campana (16:00) all'apertura della seduta
    successiva (09:30 del primo giorno feriale dopo). Fuori da quella finestra la
    lista LIVE o non ha ancora chiuso, o ha gia' ricominciato a muoversi.
    """
    try:
        d = datetime.strptime(session_date, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    nxt = d + timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += timedelta(days=1)
    return (datetime(d.year, d.month, d.day, 16, 0, tzinfo=NY_TZ),
            datetime(nxt.year, nxt.month, nxt.day, 9, 30, tzinfo=NY_TZ))


def snapshot_from_archive(editions_dir: str, edition_date: str) -> dict | None:
    """La foto di chiusura piu' recente presente in ARCHIVIO.

    Ultima rete perche' l'edizione non esca mai senza la tabella di chiusura. La
    foto porta con se' la propria seduta (`session_date`), quindi la pagina puo'
    dire a quale chiusura si riferisce: una foto piu' vecchia non e' una bugia,
    lo sarebbe spacciarla per quella di stasera.
    """
    try:
        names = sorted(n[: -len(".json")] for n in os.listdir(editions_dir) if n.endswith(".json"))
    except FileNotFoundError:
        return None
    for name in reversed([n for n in names if n < edition_date]):
        try:
            with open(os.path.join(editions_dir, f"{name}.json"), encoding="utf-8") as f:
                snap = json.load(f).get("live_close_movers")
        except (ValueError, OSError):
            continue
        if snap and (snap.get("gainers") or snap.get("losers")):
            if not snap.get("session_date"):
                snap["session_date"] = session_of_capture(snap.get("captured_at"))
            return snap
    return None


def load_live_close_movers(session_date: str, previous: dict | None,
                           editions_dir: str = EDITIONS_DIR,
                           edition_date: str | None = None) -> dict | None:
    """Lo SNAPSHOT DI CHIUSURA della lista LIVE: i top 10 / worst 10 di tutto il
    mercato USA cosi' come stavano quando Wall Street ha chiuso.

    Perche' esiste. L'edizione classifica i mover dei SOLI tre indici, chiusura su
    chiusura. La vista LIVE guarda invece tutto il mercato USA liquido, e la sua
    ultima lista della giornata E' la classifica di chiusura: senza congelarla qui,
    quella foto si perde: LIVE la sovrascrive appena riapre la borsa il giorno dopo.

    Si accetta solo una foto DAVVERO di chiusura:
      - live.json deve avere i mover (se Yahoo aveva risposto male non ci sono);
      - "market_open" deve essere FALSO: a mercati aperti sarebbe un intraday, e
        chiamarlo "alla chiusura" sarebbe scrivere una cosa non vera;
      - "updated" deve cadere nella FINESTRA di chiusura della seduta raccontata,
        cioe' tra la campana e l'apertura successiva (vedi capture_window).

    PERCHE' UNA FINESTRA E NON UN CONFRONTO DI DATE (corretto il 28 agosto 2026).
    Prima si pretendeva che la data di "updated", letta a New York, fosse identica
    a `session_date`. Regge solo se il job dell'edizione gira la sera; ma GitHub
    consegna gli schedule anche con ore di ritardo, e in quella settimana il job
    delle 21:30 UTC e' partito una volta alle 00:59 e una alle 05:33 — cioe' dopo
    la mezzanotte di New York. In quel momento "updated" portava il giorno DOPO, il
    confronto falliva, l'edizione nasceva senza foto, e non essendoci un file
    precedente da cui ereditarla la foto era persa per sempre: e' esattamente cosa
    era accaduto all'edizione del 28 agosto, che aveva perso la chiusura del 27
    (OKTA +28,63%, primo di tutto il mercato e fuori dai tre indici — cioe' il
    titolo per cui questa tabella esiste). La domanda giusta non e' "in che giorno
    e' stata scritta la foto" ma "la foto contiene la chiusura di questa seduta":
    e la risposta e' la finestra campana -> apertura successiva. Come effetto
    secondario regge anche se qualcuno riscrive live.json nella notte con gli
    stessi numeri, che e' l'altro modo in cui la foto si perdeva.

    Se nessuna condizione regge si ripiega, in ordine: sullo snapshot che
    l'edizione aveva GIA' (rigenerarla il giorno dopo non deve cancellare la foto
    di ieri sera), poi sulla foto piu' recente in archivio. Cosi' la tabella di
    chiusura non manca mai, ed e' sempre etichettata con la seduta che ritrae.
    """
    fallback = previous or snapshot_from_archive(editions_dir, edition_date or session_date)

    try:
        with open(LIVE_FILE, encoding="utf-8") as f:
            live = json.load(f)
    except (FileNotFoundError, ValueError, OSError):
        return fallback

    movers = live.get("movers") or {}
    if not (movers.get("gainers") or movers.get("losers")):
        return fallback
    if live.get("market_open"):
        return fallback  # intraday, non una chiusura

    window = capture_window(session_date)
    if not window:
        return fallback
    try:
        updated = datetime.strptime(live["updated"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (KeyError, ValueError):
        return fallback
    if not (window[0] <= updated.astimezone(NY_TZ) < window[1]):
        return fallback  # foto di un'altra seduta

    return {
        "captured_at": live["updated"],
        # La seduta ritratta, dentro la foto: cosi' resta leggibile anche quando la
        # foto viene ereditata da un'edizione precedente, e la pagina puo' dirlo.
        "session_date": session_date,
        "universe": movers.get("universe"),
        "gainers": movers.get("gainers", []),
        "losers": movers.get("losers", []),
    }


def top_markets_items(feed_raw: list[dict], weekend_report: dict | None) -> list[dict]:
    """Le notizie top della sezione "Mercati" del giorno, per la riga laterale.

    Weekend: dal digest gia' ordinato di weekend_edition.py (la sezione "mercati",
    che li' si chiama "Mercati e macro"). Giorno feriale: dal feed del giorno,
    categoria "mercati", nell'ordine in cui e' arrivato. In entrambi i casi si
    tengono solo i primi TOP_MARKETS_NEWS: e' un riassunto, non l'elenco completo.
    """
    if weekend_report:
        items = next((s.get("items", []) for s in weekend_report.get("sections", [])
                      if s.get("key") == "mercati"), [])
    else:
        items = [i for i in feed_raw if i.get("category") == "mercati"]
    return [
        {"title": i.get("title", ""), "source": i.get("source", ""), "link": i.get("link", "")}
        for i in items[:TOP_MARKETS_NEWS]
    ]


def load_markets_brief(edition_date: str) -> dict | None:
    """La prosa "Top Mercati" scritta da Claude per QUESTA edizione, se esiste.

    Chiave sulla data dell'edizione (non della seduta): le notizie di sabato non
    sono quelle di domenica, quindi un file di ieri non va riusato oggi.
    """
    try:
        with open(MARKETS_BRIEF_FILE, encoding="utf-8") as f:
            mb = json.load(f)
    except (FileNotFoundError, ValueError):
        return None
    return mb if mb.get("edition_date") == edition_date else None


def headline_for(session_date: str, stats: dict, gainers: list[dict], lang: str, manual_headline: str | None) -> str:
    if manual_headline:
        return manual_headline
    if lang == "it":
        if stats["n_up"] > stats["n_down"] * 1.5:
            tone = "Seduta ampiamente positiva a Wall Street"
        elif stats["n_down"] > stats["n_up"] * 1.5:
            tone = "Seduta in prevalenza negativa a Wall Street"
        else:
            tone = "Seduta mista a Wall Street"
        top = gainers[0] if gainers else None
        if top:
            return f"{tone}: {top['name']} {fmt_pct(top['pct_change'], 'it')} guida i rialzi"
        return tone
    else:
        if stats["n_up"] > stats["n_down"] * 1.5:
            tone = "Broadly positive session on Wall Street"
        elif stats["n_down"] > stats["n_up"] * 1.5:
            tone = "Broadly negative session on Wall Street"
        else:
            tone = "Mixed session on Wall Street"
        top = gainers[0] if gainers else None
        if top:
            return f"{tone}: {top['name']} {fmt_pct(top['pct_change'], 'en')} leads gainers"
        return tone


def main():
    force = "--force" in sys.argv

    with open(DATA_FILE) as f:
        data = json.load(f)
    companies = data["companies"]
    session_date = data.get("generated_at")
    edition_date = datetime.now().strftime("%Y-%m-%d")

    os.makedirs(EDITIONS_DIR, exist_ok=True)
    out_path = os.path.join(EDITIONS_DIR, f"{edition_date}.json")
    if os.path.exists(out_path) and not force:
        print(f"Edizione {edition_date} gia' presente: {out_path} (usa --force per rigenerarla)")
        return

    # Il bivio: recap (digest "mercati chiusi") oppure edizione di seduta coi top
    # gainer/loser. Il recap vale SOLO nei giorni davvero senza contrattazioni —
    # sabato e domenica. Un giorno feriale ha una seduta, quindi l'edizione mostra
    # sempre i suoi mover.
    #
    # Il guard sul weekend e' nato da un bug reale: se il build viene rilanciato
    # DOPO la mezzanotte italiana ma prima dell'apertura di Wall Street (quindi
    # l'ora locale e' gia' il giorno feriale dopo, mentre l'ultima seduta chiusa e'
    # ancora quella di ieri), la sola regola "questa seduta l'ha gia' raccontata
    # l'edizione precedente" scattava e trasformava un normale martedi' mattina in
    # un recap "mercati chiusi lunedi'" — falso, lunedi' la borsa era aperta.
    # Legando il recap al giorno della settimana, un feriale non viene mai piu'
    # etichettato "chiuso": al massimo, se rilanciato di mattina, ripete i mover
    # della seduta precedente (che e' esattamente cio' che deve mostrare fino alla
    # chiusura di oggi). Vedi weekend_edition.py.
    prev = weekend_edition.previous_edition(EDITIONS_DIR, edition_date)

    # Guardia anti-regressione: non pubblicare mai un'edizione la cui seduta e'
    # PIU' VECCHIA dell'ultima gia' uscita. Le sedute non tornano indietro nel
    # tempo, quindi una seduta che regredisce non e' una seduta vera: e' un fetch
    # rimasto indietro. Capita sui runner GitHub, dove yfinance ogni tanto serve
    # dati fermi al giorno prima; senza guardia un run di meta' giornata
    # sovrascriveva l'edizione buona e il sito finiva a mostrare "seduta del 14"
    # mentre l'edizione della sera prima raccontava gia' la seduta del 17.
    # Una seduta UGUALE resta lecita: weekend e feste ripetono la seduta di
    # riferimento (il recap sotto vive apposta). Solo lo STRETTAMENTE piu' vecchio
    # viene rifiutato, lasciando in piedi l'ultima edizione buona.
    prev_session = prev.get("session_date") if prev else None
    if prev_session and session_date and session_date < prev_session:
        print(
            f"Seduta {session_date} piu' vecchia dell'ultima pubblicata "
            f"({prev_session}): dati di mercato non aggiornati. Non sovrascrivo "
            f"l'edizione buona — rilancia quando il fetch e' fresco.",
            file=sys.stderr,
        )
        return

    is_weekend_day = datetime.strptime(edition_date, "%Y-%m-%d").weekday() >= 5  # 5=sabato, 6=domenica
    is_recap = is_weekend_day and weekend_edition.is_recap_edition(session_date, prev)

    # Un recap non deve MAI ereditare il commento della seduta: quel testo parla
    # dei mover di venerdi', che qui non compaiono. Il suo commento e' un altro
    # file, scritto per la data dell'edizione.
    manual = None if is_recap else load_manual_summary(session_date)
    weekend_manual = load_weekend_summary(edition_date) if is_recap else None

    auto_report_by_index = {}
    for index_key in INDEX_KEYS:
        if index_key == "combined":
            # Unione deduplicata dei SOLI tre indici USA (vedi US_INDEX_KEYS): non
            # "companies" per intero, altrimenti il FTSE MIB (valuta e orari
            # diversi) finirebbe sommato dentro il totale di Wall Street.
            subset = [c for c in companies if set(c.get("indices") or []) & set(US_INDEX_KEYS)]
        else:
            subset = [c for c in companies if index_key in (c.get("indices") or ["sp500"])]
        stats, gainers, losers = build_stats_and_movers(subset)
        auto_report_by_index[index_key] = {
            "stats": stats,
            "gainers": gainers,
            "losers": losers,
            "paragraphs": {
                "en": build_paragraphs(index_key, stats, gainers, losers, session_date, "en"),
                "it": build_paragraphs(index_key, stats, gainers, losers, session_date, "it"),
            },
        }

    # Campo di livello radice "auto_report": stesso identico contenuto di sempre
    # (solo S&P 500, solo italiano) — punta agli stessi oggetti di
    # auto_report_by_index["sp500"], cosi' le due viste non possono mai divergere.
    sp500_block = auto_report_by_index["sp500"]
    legacy_auto_report = {
        "stats": sp500_block["stats"],
        "paragraphs": sp500_block["paragraphs"]["it"],
        "gainers": sp500_block["gainers"],
        "losers": sp500_block["losers"],
    }

    # --- il riassunto del fine settimana, quando non c'e' una seduta nuova -----
    weekend_report = None
    feed_raw = load_feed_raw()
    if is_recap:
        # I segnali si recuperano da qui e non da un passo del workflow: il file
        # daily.yml su GitHub si modifica solo dall'editor web (le credenziali
        # locali non hanno lo scope "workflow" — vedi README), quindi una
        # funzionalita' che richiedesse un passo in piu' resterebbe inattiva
        # online. Sono una dozzina di quotazioni, non i 15 minuti di fetch_news.
        try:
            import fetch_weekend_signals

            fetch_weekend_signals.ensure(session_date)
        except Exception as e:
            print(
                f"ATTENZIONE: segnali del fine settimana non disponibili ({type(e).__name__}: {e}).",
                file=sys.stderr,
            )
        weekend_report = weekend_edition.build_report(
            edition_date=edition_date,
            session_date=session_date,
            session_date_label={"en": english_date(session_date), "it": italian_date(session_date)},
            feed_items=feed_raw,
            prev=prev,
            italian_date=italian_date,
            english_date=english_date,
            companies=companies,
            now=feed_fetched_at(),
        )

    if weekend_report:
        headline_it = weekend_report["headline"]["it"]
        headline_en = weekend_report["headline"]["en"]
        # Il feed sotto il digest mostra SOLO cio' che il digest non ha gia'
        # mostrato, e solo dalla finestra di questo giorno: due notizie uguali
        # nella stessa pagina sono lo stesso difetto in scala ridotta.
        feed = load_feed_items(weekend_report["feed_leftover"])
    else:
        manual_headline_it = (manual or {}).get("headline")
        manual_headline_en = (manual or {}).get("headline_en")
        headline_it = headline_for(session_date, sp500_block["stats"], sp500_block["gainers"], "it", manual_headline_it)
        headline_en = headline_for(session_date, sp500_block["stats"], sp500_block["gainers"], "en", manual_headline_en)
        feed = load_feed_items(feed_raw)

    edition = {
        "edition_date": edition_date,
        "edition_date_it": italian_date(edition_date),
        "edition_date_en": english_date(edition_date),
        "session_date": session_date,
        "session_date_it": italian_date(session_date),
        "session_date_en": english_date(session_date),
        "edition_kind": "weekend_recap" if is_recap else "session",
        "headline": headline_it,
        "headline_en": headline_en,
        "auto_report": legacy_auto_report,
        "auto_report_by_index": auto_report_by_index,
        "manual_commentary_html": (manual or {}).get("summary_html_it") or (manual or {}).get("summary_html"),
        "manual_commentary_html_en": (manual or {}).get("summary_html_en"),
        "manual_highlights": (manual or {}).get("highlights", []),
        "feed": feed,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    # Riga laterale "Top Mercati": prosa di Claude se scritta per oggi, altrimenti
    # la lista dei titoli top (sempre presente, cosi' il blocco non e' mai vuoto).
    mb = load_markets_brief(edition_date)
    edition["markets_brief"] = {
        "items": top_markets_items(feed_raw, weekend_report),
        "prose_html": (mb or {}).get("prose_html_it"),
        "prose_html_en": (mb or {}).get("prose_html_en"),
    }

    # Foto di chiusura della lista LIVE, congelata per tutto il giorno dopo. Si
    # rilegge lo snapshot gia' presente nel file, per non perderlo se questa
    # rigenerazione avviene quando live.json e' gia' passato alla seduta nuova.
    prev_snapshot = None
    if os.path.exists(out_path):
        try:
            with open(out_path, encoding="utf-8") as f:
                prev_snapshot = json.load(f).get("live_close_movers")
        except (ValueError, OSError):
            prev_snapshot = None
        # Le foto scritte prima del 28 agosto 2026 non portano la propria seduta:
        # si ricava dall'istante di scrittura, altrimenti la pagina non saprebbe
        # che chiusura sta mostrando.
        if prev_snapshot and not prev_snapshot.get("session_date"):
            prev_snapshot["session_date"] = session_of_capture(prev_snapshot.get("captured_at"))
    snapshot = load_live_close_movers(session_date, prev_snapshot, EDITIONS_DIR, edition_date)
    if snapshot:
        edition["live_close_movers"] = snapshot

    if weekend_report:
        edition["weekend_report"] = weekend_report
        edition["weekend_commentary_html"] = (weekend_manual or {}).get("summary_html_it")
        edition["weekend_commentary_html_en"] = (weekend_manual or {}).get("summary_html_en")
        # Anche in cima all'edizione, non solo dentro weekend_report: l'elenco
        # dell'archivio sul sito legge pochi campi di primo livello, e senza
        # questi mostrerebbe "seduta del 14 agosto" su tre righe consecutive —
        # cioe' la ripetizione, spostata dalla pagina all'archivio.
        edition["covers_date_it"] = weekend_report["covers_date_it"]
        edition["covers_date_en"] = weekend_report["covers_date_en"]

    with open(out_path, "w") as f:
        json.dump(edition, f, indent=2, ensure_ascii=False)

    if weekend_report:
        w = weekend_report
        n_signals = len(weekend_edition.flat_signals(w.get("signals")))
        print(
            f"Edizione creata: {out_path}  [RIASSUNTO FINE SETTIMANA]\n"
            f"  {edition['edition_date_it']} — nessuna seduta nuova (l'ultima, "
            f"{edition['session_date_it']}, e' gia' uscita ieri: qui non si ripete)\n"
            f"  notizie di {w['covers_date_it']}: {w['n_items']} nella finestra di {w['window_hours']}h "
            f"da {w['n_sources']} testate, {w['n_digest']} nel digest e {len(edition['feed'])} nel feed\n"
            f"  cosa guardare: {len(w['watchlist'])} titoli, segnali di mercato: {n_signals} strumenti, "
            f"segnali di nicchia: {len(w['niche_signals'])} societa'\n"
            f"  commento discorsivo: {'presente' if weekend_manual else 'assente (solo resoconto automatico)'}"
        )
    else:
        print(
            f"Edizione creata: {out_path}\n"
            f"  titolo edizione: {edition['edition_date_it']} (seduta del {edition['session_date_it']})\n"
            f"  indici: " + ", ".join(f"{k} ({auto_report_by_index[k]['stats']['n_total']} titoli)" for k in INDEX_KEYS) + "\n"
            f"  {len(edition['feed'])} notizie nel feed, "
            f"commento manuale: {'presente' if manual else 'assente (solo resoconto automatico)'}"
        )


if __name__ == "__main__":
    main()
