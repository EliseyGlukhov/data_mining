import json
import math
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd

DB_PATH = Path("db/warehouse.db")
SCHEMA  = Path("db/schema.sql")
CLEAN   = Path("clean/dataset.parquet")
AUTHORS = Path("clean/authors.parquet")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(SCHEMA.read_text(encoding="utf-8"))


BOOK_FIELDS = ("book_key","title","author_key","price","price_currency","rating",
               "availability","category","isbn","publish_year","source","source_url",
               "parser_version","collected_at")
AUTHOR_FIELDS = ("author_key","name","birth_date","work_count","source",
                 "source_url","parser_version","collected_at")


def _as_tuple(rec, fields):
    return tuple(rec.get(f) for f in fields)


def _is_empty(val) -> bool:
    if val is None:
        return True
    if isinstance(val, float) and math.isnan(val):
        return True
    try:
        if pd.isna(val):
            return True
    except (TypeError, ValueError):
        pass
    return False


def _eq(f, old, new) -> bool:
    old_empty = _is_empty(old)
    new_empty = _is_empty(new)
    
    if old_empty and new_empty:
        return True
    if old_empty or new_empty:
        return False

    if f == "price":
        try:
            return Decimal(str(old)).quantize(Decimal('0.01')) == Decimal(str(new)).quantize(Decimal('0.01'))
        except (InvalidOperation, ValueError):
            return False
    if f in ("rating", "publish_year", "work_count"):
        try:
            return int(old) == int(new)
        except (TypeError, ValueError):
            return False
            
    return str(old).strip() == str(new).strip()


def upsert_author(conn, rec) -> str:
    existing = conn.execute("SELECT * FROM authors WHERE author_key = ?", (rec["author_key"],)).fetchone()
    if existing is None:
        conn.execute(f"INSERT INTO authors ({','.join(AUTHOR_FIELDS)}, updated_at) "
                     f"VALUES ({','.join('?'*len(AUTHOR_FIELDS))}, ?)",
                     (*_as_tuple(rec, AUTHOR_FIELDS), now_iso()))
        return "inserted"
        
    if all(_eq(f, existing[f], rec.get(f)) for f in ("name", "birth_date", "work_count")):
        return "unchanged"
        
    conn.execute("UPDATE authors SET name=?, birth_date=?, work_count=?, updated_at=? WHERE author_key=?",
                 (rec["name"], rec.get("birth_date"), rec.get("work_count"), now_iso(), rec["author_key"]))
    return "updated"


def upsert_book(conn, rec) -> str:
    existing = conn.execute("SELECT * FROM books WHERE book_key = ?", (rec["book_key"],)).fetchone()
    if existing is None:
        conn.execute(f"INSERT INTO books ({','.join(BOOK_FIELDS)}, updated_at) "
                     f"VALUES ({','.join('?'*len(BOOK_FIELDS))}, ?)",
                     (*_as_tuple(rec, BOOK_FIELDS), now_iso()))
        conn.execute(
            "INSERT INTO book_history (book_key,title,author_key,price,price_currency,rating,availability,"
            "category,isbn,publish_year,source,valid_from,valid_to,is_current) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL,1)",
            (*_as_tuple(rec, ("book_key","title","author_key","price","price_currency","rating",
                              "availability","category","isbn","publish_year","source")), now_iso()))
        return "inserted"

    cmp_fields = ("title","author_key","price","price_currency","rating",
                  "availability","category","isbn","publish_year","source")
    diffs = [f for f in cmp_fields if not _eq(f, existing[f], rec.get(f))]
    
    if not diffs:
        return "unchanged"

    conn.execute("UPDATE book_history SET valid_to=?, is_current=0 "
                 "WHERE book_key=? AND is_current=1", (now_iso(), rec["book_key"]))

    sets = ", ".join(f"{f}=?" for f in diffs)
    conn.execute(f"UPDATE books SET {sets}, updated_at=? WHERE book_key=?",
                 (*[rec[f] for f in diffs], now_iso(), rec["book_key"]))

    conn.execute(
        "INSERT INTO book_history (book_key,title,author_key,price,price_currency,rating,availability,"
        "category,isbn,publish_year,source,valid_from,valid_to,is_current) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL,1)",
        (*_as_tuple(rec, ("book_key","title","author_key","price","price_currency","rating",
                          "availability","category","isbn","publish_year","source")), now_iso()))
    return "updated"


def run_upload(df_books, df_authors, mutation: dict | None = None) -> dict:
    run_started = now_iso()
    stats = {"inserted": 0, "updated": 0, "unchanged": 0, "rejected": 0}
    
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("INSERT INTO load_runs (started_at) VALUES (?)", (run_started,))
        run_id = cur.lastrowid

        if df_authors is not None:
            for rec in df_authors.to_dict("records"):
                r = upsert_author(conn, rec)
                stats[r] += 1

        for rec in df_books.to_dict("records"):
            if mutation and rec["book_key"] in mutation:
                rec = {**rec, **mutation[rec["book_key"]]}
            r = upsert_book(conn, rec)
            stats[r] += 1

        cur.execute(
            "UPDATE load_runs SET finished_at=?, rows_inserted=?, rows_updated=?, "
            "rows_unchanged=?, rows_rejected=? WHERE run_id=?",
            (now_iso(), stats["inserted"], stats["updated"], stats["unchanged"], stats["rejected"], run_id))
        conn.commit()
    return {"run_id": run_id, **stats}


if __name__ == "__main__":
    init_db()
    df = pd.read_parquet(CLEAN)
    df["price"] = df["price"].astype(object)
    df_a = pd.read_parquet(AUTHORS) if AUTHORS.exists() else None

    print("Run 1:", run_upload(df, df_a))
    print("Run 2:", run_upload(df, df_a))

    two = df.head(2)["book_key"].tolist()
    mutation = {two[0]: {"title": df.iloc[0]["title"] + " (2nd ed.)"},
                two[1]: {"rating": 5 if df.iloc[1]["rating"] != 5 else 4}}
    print("Run 3:", run_upload(df, df_a, mutation))

    with sqlite3.connect(DB_PATH) as conn:
        try:
            conn.execute("INSERT INTO books (book_key,title,rating,source,source_url,parser_version,collected_at,updated_at) "
                         "VALUES ('bad',  'X', 9, 'html_books_toscrape','u','v','2025','2025')")
        except sqlite3.IntegrityError as e:
            print("CHECK rejected:", e)
        try:
            conn.execute("INSERT INTO books (book_key,title,source,source_url,parser_version,collected_at,updated_at) "
                         "SELECT book_key, title, source, source_url, parser_version, collected_at, updated_at "
                         "FROM books LIMIT 1")
        except sqlite3.IntegrityError as e:
            print("PK rejected:", e)