import json, re, sys, time, urllib.parse
from datetime import datetime, timezone
from pathlib import Path
import requests
from bs4 import BeautifulSoup

RAW = Path("raw")
RAW.mkdir(exist_ok=True)
OUT = RAW / "html_books_toscrape.jsonl"
BASE = "https://books.toscrape.com/catalogue/"
PARSER_VERSION = "html-1.0.0"
HEADERS = {"User-Agent": "lab6"}

RATING_MAP = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}


def collect(pages: int = 10) -> None:
    with open(OUT, "a", encoding="utf-8") as f:
        for page in range(1, pages + 1):
            listing = f"{BASE}page-{page}.html"
            r = requests.get(listing, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            for art in soup.select("article.product_pod"):
                link = art.select_one("h3 a")
                rel = link["href"]
                title = link["title"]
                price_raw = art.select_one("p.price_color").get_text(strip=True)
                rating_raw = [c for c in art.select_one("p.star-rating")["class"] if c != "star-rating"][0]
                avail_raw = art.select_one("p.instock.availability").get_text(strip=True)

                detail_url = urllib.parse.urljoin(listing, rel)
                det = requests.get(detail_url, headers=HEADERS, timeout=15)
                ds = BeautifulSoup(det.text, "html.parser")

                crumbs = ds.select("ul.breadcrumb li a")
                category = crumbs[2].get_text(strip=True) if len(crumbs) > 2 else None

                upc = None
                for tr in ds.select("table.table-striped tr"):
                    th, td = tr.select_one("th"), tr.select_one("td")
                    if th and td and th.get_text(strip=True) == "UPC":
                        upc = td.get_text(strip=True); break

                rec = {
                    "_source": "html_books_toscrape",
                    "_source_url": detail_url,
                    "_collected_at": datetime.now(timezone.utc).isoformat(),
                    "_parser_version": PARSER_VERSION,
                    "_status": r.status_code,
                    "title": title,
                    "price_raw": price_raw,
                    "rating_raw": rating_raw,
                    "availability_raw": avail_raw,
                    "category_raw": category,
                    "upc_raw": upc,
                    "relative_url": rel,
                }
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                time.sleep(0.1)
            time.sleep(0.5)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    collect(n)