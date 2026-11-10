import json
import sqlite3
import sys

def load_stats(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def main(current_stats_path, previous_stats_path, db_path):
    cur = load_stats(current_stats_path)
    prev = load_stats(previous_stats_path)

    cur_items = cur.get("item_scraped_count", 0)
    prev_items = prev.get("item_scraped_count", 0)
    warnings = []

    # 1. Падение числа записей > 20%
    if prev_items > 0 and cur_items < prev_items * 0.8:
        warnings.append(
            f"ITEM COUNT DROP: current={cur_items}, previous={prev_items}, "
            f"drop={100 * (1 - cur_items / prev_items):.1f}% > 20%"
        )

    # 2. Доля пустых обязательных полей > 5%
    required = ["title", "category", "price_excl_tax",
                "availability", "number_of_reviews", "upc"]
    conn = sqlite3.connect(db_path)
    cur_db = conn.cursor()
    cur_db.execute(f"SELECT COUNT(*) FROM books")
    total = cur_db.fetchone()[0]
    if total > 0:
        for field in required:
            cur_db.execute(f"SELECT COUNT(*) FROM books WHERE {field} IS NULL OR {field} = ''")
            empty = cur_db.fetchone()[0]
            share = empty / total
            if share > 0.05:
                warnings.append(
                    f"EMPTY FIELD > 5%: {field} = {share:.1%} ({empty}/{total})"
                )
    conn.close()

    if warnings:
        print("SMOKE-CHECK FAILED")
        for w in warnings:
            print(" -", w)
        sys.exit(1)
    else:
        print("SMOKE-CHECK PASSED")
        sys.exit(0)

if __name__ == "__main__":
    main(
        current_stats_path="data/stats_current.json",
        previous_stats_path="data/stats_previous.json",
        db_path="data/crawl.db",
    )