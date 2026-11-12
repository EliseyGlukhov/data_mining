import json, sys, time, urllib.parse
from datetime import datetime, timezone
from pathlib import Path
import requests

RAW = Path("raw"); RAW.mkdir(exist_ok=True)
BOOKS_OUT = RAW / "api_openlibrary_books.jsonl"
AUTH_OUT = RAW / "api_openlibrary_authors.jsonl"
BASE = "https://openlibrary.org"
PARSER_VERSION = "api-1.0.0"
HEADERS = {"User-Agent": "lab6"}
FIELDS = "key,title,author_name,author_key,first_publish_year,isbn,language,publisher"


def collect(queries, limit=30):
    seen_authors: set[str] = set()
    with open(BOOKS_OUT, "a", encoding="utf-8") as fb, open(AUTH_OUT, "a", encoding="utf-8") as fa:
        for q in queries:
            params = {"q": q, "limit": limit, "fields": FIELDS}
            url = f"{BASE}/search.json?{urllib.parse.urlencode(params)}"
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.status_code != 200:
                continue
            for doc in r.json().get("docs", []):
                isbns = doc.get("isbn") or []
                book_rec = {
                    "_source": "openlibrary_api",
                    "_source_url": url,
                    "_collected_at": datetime.now(timezone.utc).isoformat(),
                    "_parser_version": PARSER_VERSION,
                    "_status": r.status_code,
                    "key": doc.get("key"),
                    "title": doc.get("title"),
                    "author_names": doc.get("author_name", []),
                    "author_keys": doc.get("author_key", []),
                    "first_publish_year": doc.get("first_publish_year"),
                    "isbn_candidates": isbns[:3],
                }
                fb.write(json.dumps(book_rec, ensure_ascii=False) + "\n")

                for name, akey in zip(doc.get("author_name", []), doc.get("author_key", [])):
                    if akey in seen_authors:
                        continue
                    seen_authors.add(akey)
                    a_rec = {
                        "_source": "openlibrary_api_author",
                        "_source_url": f"{BASE}/authors/{akey}.json",
                        "_collected_at": datetime.now(timezone.utc).isoformat(),
                        "_parser_version": PARSER_VERSION,
                        "_status": 200,
                        "author_key": akey,
                        "name": name,
                    }
                    fa.write(json.dumps(a_rec, ensure_ascii=False) + "\n")
            time.sleep(1)


if __name__ == "__main__":
    collect(["programming", "data science", "python", "machine learning", "databases"])