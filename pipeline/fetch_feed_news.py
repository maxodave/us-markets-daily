"""
Costruisce il feed visuale di notizie (titolo + fonte + data + IMMAGINE + link)
leggendo direttamente i feed RSS delle testate indicate dall'utente.

Perche' non si usa Google News per questo: i link Google News sono redirect
offuscati che finiscono su un consent wall, quindi da li' non si riesce a
risalire ne' all'URL reale ne' all'immagine dell'articolo. I feed RSS delle
testate danno invece URL reali e, in molti casi, l'immagine di copertina.

Le immagini vengono prese da:
  1. campi media RSS (media:content / media:thumbnail / enclosure), quando presenti;
  2. altrimenti dal tag og:image della pagina dell'articolo (solo per i primi
     IMG_FETCH_LIMIT articoli, per non allungare troppo l'esecuzione).

Le immagini NON vengono scaricate: si linkano (hotlink) al server della testata,
con fonte e link all'articolo sempre visibili. Vedi nota in README sul riuso
delle immagini se un giorno la pagina venisse pubblicata online.

Uso:
    python3 fetch_feed_news.py
"""
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
import requests

OUT_FILE = "feed_news.json"
MAX_PER_FEED = 12
IMG_FETCH_LIMIT = 60
IMG_WORKERS = 8
HTTP_TIMEOUT = 15
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124 Safari/537.36"
    )
}

# (etichetta, url_feed, categoria). I feed morti vengono ignorati silenziosamente.
FEEDS = [
    # --- mercati / finanza ---
    ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex", "mercati"),
    ("Bloomberg", "https://feeds.bloomberg.com/markets/news.rss", "mercati"),
    # Reuters e Barron's non offrono un RSS pubblico utilizzabile (Reuters ha chiuso
    # i feed, Barron's risponde 403): si recuperano via Google News. Sono schede
    # SENZA immagine (il link e' un redirect google, non l'articolo) e col titolo
    # ripulito dal suffisso " - Testata" in collect(). Vedi anche backfill_images().
    ("Reuters", "https://news.google.com/rss/search?q=site:reuters.com+business+when:2d&hl=en-US&gl=US&ceid=US:en", "mercati"),
    ("Barron's", "https://news.google.com/rss/search?q=site:barrons.com+when:2d&hl=en-US&gl=US&ceid=US:en", "mercati"),
    ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories", "mercati"),
    ("The Wall Street Journal", "https://feeds.content.dowjones.io/public/rss/RSSMarketsMain", "mercati"),
    ("Financial Times", "https://www.ft.com/rss/home", "mercati"),
    ("Financial Times", "https://www.ft.com/companies?format=rss", "mercati"),
    ("CNBC", "https://www.cnbc.com/id/20910258/device/rss/rss.html", "mercati"),
    ("CNBC", "https://www.cnbc.com/id/100003114/device/rss/rss.html", "mercati"),
    ("The New York Times", "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml", "mercati"),
    ("Forbes", "https://www.forbes.com/business/feed/", "mercati"),
    ("CNN", "http://rss.cnn.com/rss/money_news_international.rss", "mercati"),
    ("The Economist", "https://www.economist.com/finance-and-economics/rss.xml", "mercati"),
    # --- italiane ---
    ("ANSA Economia", "https://www.ansa.it/sito/notizie/economia/economia_rss.xml", "italia"),
    ("Wall Street Italia", "https://www.wallstreetitalia.com/feed/", "italia"),
    ("FinanzaOnline", "https://www.finanzaonline.com/feed/", "italia"),
    # --- crypto ---
    ("Cointelegraph", "https://cointelegraph.com/rss", "crypto"),
    ("Decrypt", "https://decrypt.co/feed", "crypto"),
    ("The Block", "https://www.theblock.co/rss.xml", "crypto"),
    ("The Cryptonomist", "https://cryptonomist.ch/feed/", "crypto"),
    # --- tech / scienza ---
    ("Wired", "https://www.wired.com/feed/rss", "tech"),
    ("Wired Italia", "https://www.wired.it/feed/rss", "tech"),
    ("TechCrunch", "https://techcrunch.com/feed/", "tech"),
    ("Nature", "https://www.nature.com/nature.rss", "scienza"),
    ("MIT Technology Review", "https://www.technologyreview.com/feed/", "scienza"),
]

OG_IMAGE_RE = re.compile(
    r"<meta[^>]+(?:property|name)=[\"']og:image[\"'][^>]+content=[\"']([^\"']+)", re.I
)


def image_from_entry(entry) -> str | None:
    for key in ("media_content", "media_thumbnail"):
        items = entry.get(key) or []
        for it in items:
            url = it.get("url")
            if url:
                return url
    for link in entry.get("links", []) or []:
        if link.get("rel") == "enclosure" and "image" in (link.get("type") or "image"):
            if link.get("href"):
                return link["href"]
    blob = (entry.get("summary") or "") + str(entry.get("content") or "")
    m = re.search(r"<img[^>]+src=[\"']([^\"']+)", blob)
    return m.group(1) if m else None


def fetch_og_image(url: str) -> str | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=HTTP_TIMEOUT)
        if r.status_code != 200:
            return None
        m = OG_IMAGE_RE.search(r.text)
        return m.group(1) if m else None
    except Exception:
        return None


def parse_dt(entry):
    try:
        return parsedate_to_datetime(entry.get("published", ""))
    except Exception:
        return None


def clean_summary(entry) -> str:
    raw = entry.get("summary") or ""
    text = re.sub(r"<[^>]+>", " ", raw)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:280]


def norm_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", title.lower())[:70]


def collect() -> list[dict]:
    seen_links: set[str] = set()
    seen_titles: set[str] = set()
    items: list[dict] = []
    for source, url, category in FEEDS:
        try:
            d = feedparser.parse(url)
        except Exception as e:
            print(f"  ! {source}: {e}")
            continue
        if not d.entries:
            print(f"  - {source}: feed vuoto/non raggiungibile, ignorato")
            continue
        added = 0
        for e in d.entries[:MAX_PER_FEED]:
            link = e.get("link")
            if not link or link in seen_links:
                continue
            nt = norm_title(e.get("title") or "")
            if not nt or nt in seen_titles:
                continue  # stessa storia ripubblicata da un'altra testata del gruppo
            seen_links.add(link)
            seen_titles.add(nt)
            dt = parse_dt(e)
            title = (e.get("title") or "").strip()
            # Google News aggiunge " - Testata" in coda al titolo: la fonte la
            # mostriamo gia' noi (l'etichetta del feed), quindi si toglie.
            if "news.google.com" in url:
                title = title.rsplit(" - ", 1)[0].strip()
            items.append(
                {
                    "title": title,
                    "source": source,
                    "category": category,
                    "published": e.get("published", ""),
                    "published_dt": dt,
                    "link": link,
                    "summary": clean_summary(e),
                    "image": image_from_entry(e),
                }
            )
            added += 1
        print(f"  + {source}: {added} articoli")
    items.sort(key=lambda x: x["published_dt"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return items


def backfill_images(items: list[dict]) -> None:
    # I link di Google News (Reuters/Barron's) sono redirect, non l'articolo: il
    # fetch og:image non troverebbe nulla e sprecherebbe solo tempo — si saltano.
    missing = [i for i in items[:IMG_FETCH_LIMIT] if not i["image"] and "news.google.com" not in i["link"]]
    if not missing:
        return
    print(f"\nRecupero og:image per {len(missing)} articoli senza immagine nel feed...")
    with ThreadPoolExecutor(max_workers=IMG_WORKERS) as pool:
        futures = {pool.submit(fetch_og_image, it["link"]): it for it in missing}
        for fut in as_completed(futures):
            it = futures[fut]
            try:
                it["image"] = fut.result()
            except Exception:
                it["image"] = None


def main():
    print(f"Recupero feed RSS da {len(FEEDS)} sorgenti...")
    items = collect()
    backfill_images(items)

    for it in items:
        it.pop("published_dt", None)

    with_img = sum(1 for i in items if i["image"])
    out = {
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "count": len(items),
        "with_image": with_img,
        "items": items,
    }
    with open(OUT_FILE, "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print(f"\nCompletato: {len(items)} articoli ({with_img} con immagine) salvati in {OUT_FILE}")


if __name__ == "__main__":
    main()
