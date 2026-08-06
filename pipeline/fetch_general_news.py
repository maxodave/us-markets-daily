"""
Recupera un pool di notizie generali (mercato USA, macroeconomia, e per contesto anche
crypto/tech/scienza) usando la lista completa di fonti indicata dall'utente. Il pool
serve come materiale grezzo per scrivere il riassunto narrativo del giorno
(market_summary_it.json) — vedi README per il flusso di lavoro giornaliero.

Non genera da solo un riassunto: questo script raccoglie soltanto i titoli/link.

Uso:
    python3 fetch_general_news.py
"""
import json
import urllib.parse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser

DATA_FILE = "data.json"
OUT_FILE = "general_news_pool.json"
WINDOW_DAYS = 2
MACRO_WINDOW_DAYS = 4

# Lista completa fornita dall'utente (dominio estratto dagli URL)
FULL_SITES = [
    "reuters.com", "bloomberg.com", "ft.com", "wsj.com", "cnbc.com", "marketwatch.com",
    "barrons.com", "nytimes.com", "forbes.com", "finance.yahoo.com",
    "certificatejournal.it", "finanzaonline.com", "wallstreetitalia.com", "ansa.it",
    "economist.com", "cnn.com",
    "decrypt.co", "theblockcrypto.com", "cryptonomist.ch", "cryptodaily.io", "cointelegraph.com",
    "wired.com", "wired.it", "techcrunch.com", "fondazioneleonardo.com", "nature.com", "science.org",
]
SITE_FILTER = "(" + " OR ".join(f"site:{s}" for s in FULL_SITES) + ")"

QUERIES = [
    ("market", f'("stock market" OR "Wall Street" OR "S&P 500") {SITE_FILTER} when:{WINDOW_DAYS}d'),
    ("macro", f'("Federal Reserve" OR inflation OR "jobs report" OR earnings) {SITE_FILTER} when:{MACRO_WINDOW_DAYS}d'),
    ("crypto", f'(bitcoin OR crypto OR ethereum) {SITE_FILTER} when:{WINDOW_DAYS}d'),
]


def fetch(query: str) -> list[dict]:
    url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=en-US&gl=US&ceid=US:en"
    d = feedparser.parse(url)
    out = []
    for e in d.entries:
        try:
            dt = parsedate_to_datetime(e.get("published", ""))
        except Exception:
            dt = None
        out.append(
            {
                "title": e.get("title", ""),
                "source": e.get("source", {}).get("title", ""),
                "published": e.get("published", ""),
                "published_dt": dt,
                "link": e.get("link", ""),
            }
        )
    return out


def main():
    try:
        with open(DATA_FILE) as f:
            data = json.load(f)
        reference_date_str = data.get("generated_at")
    except FileNotFoundError:
        reference_date_str = None

    seen_links = set()
    pool = []
    for category, query in QUERIES:
        print(f"Recupero notizie generali: {category}...")
        for item in fetch(query):
            if not item["link"] or item["link"] in seen_links:
                continue
            seen_links.add(item["link"])
            item["category"] = category
            pool.append(item)

    pool.sort(key=lambda x: x["published_dt"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    for item in pool:
        item.pop("published_dt", None)

    out = {"reference_date": reference_date_str, "sources_considered": FULL_SITES, "pool": pool}
    with open(OUT_FILE, "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print(f"\nCompletato: {len(pool)} notizie generali salvate in {OUT_FILE}")


if __name__ == "__main__":
    main()
