import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd

RAW = Path("raw")
CLEAN = Path("clean"); CLEAN.mkdir(exist_ok=True)

RATING_MAP = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}
CURRENCY_MAP = {"£": "GBP", "$": "USD", "€": "EUR", "₽": "RUB"}

SERVICE_FIELD_MAP = {
    "_source": "source",
    "_source_url": "source_url",
    "_parser_version": "parser_version",
    "_collected_at": "collected_at",
}

BOOK_REQUIRED = ("book_key", "title", "source", "source_url")
AUTHOR_REQUIRED = ("author_key", "name", "source", "source_url")
BOOK_COLS = ("book_key", "title", "author_key", "price", "price_currency", "rating",
             "availability", "category", "isbn", "publish_year",
             "source", "source_url", "parser_version", "collected_at")
AUTHOR_COLS = ("author_key", "name", "birth_date", "work_count",
               "source", "source_url", "parser_version", "collected_at")


def promote_service_fields(rec: dict) -> dict:
    for src, dst in SERVICE_FIELD_MAP.items():
        if src in rec and rec[src] is not None:
            rec[dst] = rec[src]
    return rec


def step1_text(rec: dict) -> dict:
    for f in ("title", "category", "availability", "category_raw",
              "availability_raw", "name"):
        if isinstance(rec.get(f), str):
            v = unicodedata.normalize("NFKC", rec[f])
            v = (v.replace("\xa0", " ")
                   .replace("\u200b", "")
                   .replace("\u200c", "")
                   .replace("\u200d", ""))
            rec[f] = re.sub(r"\s+", " ", v).strip()
    return rec


def classify(rec: dict) -> str:
    src = rec.get("_source") or rec.get("source", "")
    if src in ("openlibrary_authors", "openlibrary_api_author"):
        return "author"
    if src == "openlibrary_api":
        is_author = (
            "author_key" in rec
            and "isbn_candidates" not in rec
            and "key" not in rec
        )
        return "author" if is_author else "book"
    return "book"


def step2_key(rec: dict) -> tuple[str | None, str | None]:
    src = rec.get("_source") or rec.get("source")

    if src == "html_books_toscrape":
        upc = rec.get("upc_raw") or rec.get("upc")
        if isinstance(upc, str) and upc.strip():
            clean = re.sub(r"[^a-z0-9]", "", upc.lower())
            if len(clean) >= 6:
                return f"toscrape-upc:{clean}", None
        title = rec.get("title")
        if isinstance(title, str) and title.strip():
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
            if len(slug) >= 3:
                return f"toscrape:{slug}", None
        return None, "slug_too_short"

    if src in ("openlibrary_authors", "openlibrary_api_author"):
        akey = rec.get("author_key")
        if isinstance(akey, str) and akey.strip():
            clean = re.sub(r"[^a-z0-9]", "", akey.lower())
            if clean:
                return f"author:{clean}", None
        return None, "no_author_key"

    if src == "openlibrary_api":
        if ("author_key" in rec
                and "isbn_candidates" not in rec
                and "key" not in rec):
            akey = rec.get("author_key")
            if isinstance(akey, str) and akey.strip():
                clean = re.sub(r"[^a-z0-9]", "", akey.lower())
                return f"author:{clean}", None
            return None, "no_author_key"

        for raw in (rec.get("isbn_candidates") or []):
            if raw is None:
                continue
            d = re.sub(r"[^0-9Xx]", "", str(raw)).upper()
            if len(d) in (10, 13):
                return f"isbn:{d}", None

        ol_key = rec.get("key")
        if isinstance(ol_key, str) and ol_key.strip():
            m = re.search(r"/([^/]+)$", ol_key.strip())
            if m:
                return f"ol:{m.group(1)}", None

        title = rec.get("title")
        if isinstance(title, str) and len(title.strip()) >= 2:
            authors = rec.get("author_names") or []
            a_str = ",".join(str(a) for a in authors) if isinstance(authors, list) else ""
            h = hashlib.sha1(
                f"{title.strip().lower()}|{a_str.lower()}".encode()
            ).hexdigest()[:16]
            return f"ol-title:{h}", None

        return None, "no_business_key"

    return None, f"unknown_source:{src!r}"


def step3_types(rec: dict) -> tuple[dict, str | None]:
    for src_f, dst_f in (("availability_raw", "availability"),
                         ("category_raw",     "category"),
                         ("upc_raw",          "upc")):
        if rec.get(dst_f) in (None, "") and rec.get(src_f):
            rec[dst_f] = rec[src_f]

    if rec.get("price_raw"):
        s = rec["price_raw"]
        for sym, cur in CURRENCY_MAP.items():
            if sym in s:
                rec["price_currency"] = cur
        num = re.sub(r"[^\d.,]", "", s).replace(",", ".")
        try:
            rec["price"] = str(Decimal(num))
        except (InvalidOperation, ValueError):
            return rec, "price_unparseable"
    if rec.get("rating_raw"):
        rec["rating"] = RATING_MAP.get(rec["rating_raw"])
    if rec.get("collected_at"):
        try:
            dt = datetime.fromisoformat(str(rec["collected_at"]).replace("Z", "+00:00"))
            iso = dt.astimezone(timezone.utc).isoformat()
            rec["collected_at"] = iso
            rec["_collected_at"] = iso
        except ValueError:
            return rec, "collected_at_unparseable"
    if rec.get("first_publish_year"):
        try:
            rec["publish_year"] = int(rec["first_publish_year"])
        except (TypeError, ValueError):
            rec["publish_year"] = None
    for raw in (rec.get("isbn_candidates") or []):
        if raw is None:
            continue
        d = re.sub(r"[^0-9Xx]", "", str(raw)).upper()
        if len(d) in (10, 13):
            rec["isbn"] = d
            break

    if rec.get("source") == "openlibrary_api" and rec.get("author_keys"):
        first_author = rec["author_keys"][0]
        if isinstance(first_author, str):
            rec["author_key"] = first_author.replace("author:", "")
    
    return rec, None

def step4_missing(rec: dict, required: tuple[str, ...]) -> str | None:
    for f in required:
        v = rec.get(f)
        if v is None or (isinstance(v, str) and not v.strip()):
            return f"missing_required:{f}"
    return None

def step5_dedup(df: pd.DataFrame, log: list, key: str = "book_key") -> pd.DataFrame:
    if df.empty:
        return df
    before = len(df)
    df = df.sort_values("collected_at").drop_duplicates(subset=key, keep="last")
    log.append({"step": 5, "key": key, "before": before, "after": len(df),
                "removed": before - len(df), "note": "по бизнес-ключу, keep=last"})
    if key == "book_key" and "author_key" in df.columns:
        near_mask = df.duplicated(subset=["title", "author_key"], keep="last")
        if near_mask.any():
            n_before = len(df)
            df = df[~near_mask]
            log.append({"step": 5.1, "key": "title+author_key",
                        "before": n_before, "after": len(df),
                        "removed": n_before - len(df),
                        "note": "near-dupes"})
    return df

def business_rules(rec: dict) -> str | None:
    if rec.get("source") == "html_books_toscrape":
        if rec.get("price") is not None and Decimal(rec["price"]) > Decimal("200"):
            return "rule1:HTML price>200"
        if rec.get("rating") is not None and not (1 <= rec["rating"] <= 5):
            return "rule2:rating out of range"
        if rec.get("availability") and "stock" not in rec["availability"].lower():
            return "rule3:availability must mention stock"
    if rec.get("source") == "openlibrary_api":
        if rec.get("publish_year") and rec["publish_year"] > datetime.now().year:
            return "rule4:publish_year in future"
        if rec.get("isbn") and not rec["isbn"][:-1].isdigit():
            return "rule5:ISBN prefix not digits"
    if rec.get("title") and rec["title"].lower() in {"unknown", "untitled", "n/a"}:
        return "rule6:placeholder title"
    return None

def run() -> None:
    log: list = []
    rejects: list = []
    books: list = []
    authors: list = []
    counters = {"books_seen": 0, "authors_seen": 0, "decode_errors": 0}

    for raw_file in sorted(RAW.glob("*.jsonl")):
        with open(raw_file, encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError as e:
                    counters["decode_errors"] += 1
                    rejects.append({
                        "_file": raw_file.name, "_line_no": line_no,
                        "step": 0, "reason": f"json_decode:{e}",
                        "payload": line[:500],
                    })
                    continue

                rec["_raw_file"] = raw_file.name
                rec["_raw_line"] = line_no
                rec = promote_service_fields(rec)
                rec = step1_text(rec)
                kind = classify(rec)

                if kind == "author":
                    counters["authors_seen"] += 1
                    key, err = step2_key(rec)
                    if err:
                        rejects.append({**rec, "reason": err, "step": 2})
                        continue
                    rec["author_key"] = key.replace("author:", "")
                    err = step4_missing(rec, AUTHOR_REQUIRED)
                    if err:
                        rejects.append({**rec, "reason": err, "step": 4})
                        continue
                    if rec.get("work_count") is not None:
                        try:
                            rec["work_count"] = int(rec["work_count"])
                        except (TypeError, ValueError):
                            rec["work_count"] = None
                    authors.append(rec)
                    continue

                counters["books_seen"] += 1
                key, err = step2_key(rec)
                if err:
                    rejects.append({**rec, "reason": err, "step": 2})
                    continue
                rec["book_key"] = key
                rec, err = step3_types(rec)
                if err:
                    rejects.append({**rec, "reason": err, "step": 3})
                    continue
                err = step4_missing(rec, BOOK_REQUIRED)
                if err:
                    rejects.append({**rec, "reason": err, "step": 4})
                    continue
                err = business_rules(rec)
                if err:
                    rejects.append({**rec, "reason": err, "step": 6})
                    continue
                books.append(rec)

    df_books = pd.DataFrame(books)
    for c in BOOK_COLS:
        if c not in df_books.columns:
            df_books[c] = None
    df_books = step5_dedup(df_books, log, key="book_key")
    if not df_books.empty:
        df_books["price"] = pd.to_numeric(df_books["price"], errors="coerce")
        df_books["rating"] = pd.to_numeric(df_books["rating"], errors="coerce").astype("Int64")
        df_books["publish_year"] = pd.to_numeric(df_books["publish_year"], errors="coerce").astype("Int64")
    df_books[list(BOOK_COLS)].to_parquet(CLEAN / "dataset.parquet", index=False)

    df_auth = pd.DataFrame(authors)
    for c in AUTHOR_COLS:
        if c not in df_auth.columns:
            df_auth[c] = None
    df_auth = step5_dedup(df_auth, log, key="author_key")
    df_auth[list(AUTHOR_COLS)].to_parquet(CLEAN / "authors.parquet", index=False)

    protocol = {
        "counters": counters,
        "counts_clean": {"books": len(df_books), "authors": len(df_auth)},
        "rejected_total": len(rejects),
        "reject_breakdown": (
            pd.Series([r["reason"] for r in rejects]).value_counts().to_dict()
            if rejects else {}
        ),
        "log": log,
    }
    with open(CLEAN / "rejects.jsonl", "w", encoding="utf-8") as f:
        for r in rejects:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    with open(CLEAN / "protocol.json", "w", encoding="utf-8") as f:
        json.dump(protocol, f, ensure_ascii=False, indent=2, default=str)

    print(
        f"books={len(df_books)} authors={len(df_auth)} rejects={len(rejects)} "
        f"| seen: books={counters['books_seen']} authors={counters['authors_seen']} "
        f"decode_errors={counters['decode_errors']}"
    )
    if rejects:
        print("reject_breakdown:", protocol["reject_breakdown"])

if __name__ == "__main__":
    run()