"""
Sceglie, tra le notizie di un titolo, quella che spiega il movimento della seduta.

Modulo condiviso: lo usano build_edition.py (per il campo "reason" di ogni mover,
mostrato sul sito e nella dashboard) e build_publish.py (per la riga di ogni
mover nel post LinkedIn e nella newsletter). Sta in un file a parte proprio
perche' le due viste devono citare la STESSA notizia: se il sito dicesse una cosa
e il post un'altra per lo stesso titolo, sarebbe un errore visibile ai lettori.

Nessuna IA: sono filtri lessicali su titolo e testata.
"""

# Solo testate riconosciute: e' materiale pubblico, e la fonte citata ne definisce
# la credibilita'. Le content farm (MarketBeat, TradingKey, Traders Union,
# Quiver Quantitative, Moomoo, GuruFocus, TipRanks...) pubblicano titoli
# auto-generati e restano fuori. Se nessuna fonte affidabile spiega un movimento,
# si dichiara che non risulta un catalizzatore: e' un'informazione, non una lacuna.
TRUSTED_SOURCES = (
    "reuters", "bloomberg", "wsj", "wall street journal", "financial times",
    "cnbc", "marketwatch", "barron", "new york times", "forbes", "cnn",
    "economist", "yahoo finance", "associated press", "ansa",
    "wall street italia", "finanzaonline", "il sole 24 ore",
)

GENERIC_PATTERNS = (
    # titoli di pura azione di prezzo: non dicono il perche'
    "outperforms competitors", "underperforms", "stock quote", "stock price",
    "in real time", "advanced charts", "sec filings", "biggest moves",
    "stocks making the biggest", "movers", "most expensive stocks",
    "premarket", "after hours", "that explain today", "week ahead",
    "etf overview", "still underperforms market", "best core ideas",
    "stock 12", "price target raised to", "latest news", "closed up by",
    "closed down by", "shares down", "shares up", "exceeds market returns",
    "drivers behind the movement", "trade near", "support amid",
    # riepiloghi di seduta: nominano la societa' solo come esempio nell'elenco
    # ("...As Shopify Led, Insulet Lagged"), quindi passerebbero il controllo sul
    # nome pur non dicendo nulla su di essa.
    "indexes finished", "indexes closed", "indices finished", "indices closed",
    "stocks close", "stocks closed", "market wrap", "s&p 500 finished",
    # anteprime e contenuti da 13F: non spiegano la seduta
    "gears up to report", "what to expect", "earnings expected to",
    "ahead of next week", "stake in", "shares in", "bought by", "acquired by",
    "sells ", "buys ", "position in", "holdings in", "what to know ahead",
    "here's what to", "should you buy", "is it time to buy", "a buy, a sell",
    "prediction:", "3 reasons", "better buy",
)

CORP_SUFFIXES = {
    "inc", "inc.", "corp", "corp.", "corporation", "co", "co.", "company",
    "plc", "ltd", "llc", "holdings", "holding", "group", "technologies",
    "technology", "international", "&", "the", "sa", "nv", "ag",
}


def strip_source_suffix(title: str) -> str:
    return title.rsplit(" - ", 1)[0].strip() if " - " in title else title.strip()


def is_trusted(source: str) -> bool:
    low = (source or "").lower()
    return any(t in low for t in TRUSTED_SOURCES)


def brand_tokens(name: str) -> list[str]:
    """Token distintivi del marchio: si fermano al primo suffisso societario.

    Serve per capire se un titolo parla DAVVERO di quella societa'. Usare tutti i
    token del nome sarebbe fuorviante: per "Alexandria Real Estate Equities" le
    parole "Real Estate" fanno match con qualunque notizia sul settore.
    """
    out = []
    for raw in name.split():
        tok = raw.strip(",.").lower()
        if tok in CORP_SUFFIXES:
            break
        out.append(tok)
        if len(out) == 2:
            break
    return [t for t in out if len(t) >= 3]


def headline_is_about(title: str, mover: dict) -> bool:
    low = title.lower()
    toks = brand_tokens(mover["name"])
    if toks and all(t in low for t in toks):
        return True
    if toks and toks[0] in low:
        return True
    sym = mover["symbol"]
    return f"({sym})" in title or f"{sym}:" in title


def pick_reason(mover: dict, news_key: str = "news") -> dict | None:
    """Notizia che spiega il movimento della seduta, o None.

    Ritorna {"title", "source", "link"} col titolo gia' ripulito dal suffisso
    " - Testata" che Google News aggiunge.

    Tre requisiti, tutti necessari: la notizia deve essere RECENTE (mai lo
    storico — una notizia di giorni prima non spiega la seduta di ieri e produce
    attribuzioni contraddittorie), deve venire da una testata affidabile, e deve
    nominare la societa' senza essere un titolo generico di prezzo o un'anteprima.

    news_key esiste perche' il dato grezzo di fetch_news.py chiama il campo
    "news_recent", mentre il mover snellito dentro l'edizione lo chiama "news".

    Se nulla passa si restituisce None: dichiarare l'assenza di catalizzatore e'
    corretto, inventarne uno no.
    """
    for n in mover.get(news_key) or []:
        source = n.get("source", "")
        if not is_trusted(source):
            continue
        t = strip_source_suffix(n.get("title", ""))
        if not t or len(t) < 25:
            continue
        low = t.lower()
        if any(g in low for g in GENERIC_PATTERNS):
            continue
        if not headline_is_about(t, mover):
            continue
        return {"title": t, "source": source, "link": n.get("link", "")}
    return None
