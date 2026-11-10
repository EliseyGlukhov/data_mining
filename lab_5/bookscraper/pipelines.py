import re
import sqlite3
from scrapy.exceptions import DropItem

class ValidationPipeline:
    """Проверка обязательных полей; DropItem + stats.inc_value("dropped/missing_fields")"""

    REQUIRED = ["upc", "title", "price_excl_tax", "availability",
                "number_of_reviews", "category", "description"]

    def process_item(self, item, spider):
        missing = [f for f in self.REQUIRED if not item.get(f)]
        if missing:
            spider.crawler.stats.inc_value("dropped/missing_fields")
            raise DropItem(f"Missing fields: {missing}; UPC={item.get('upc')}")
        return item

class CleaningPipeline:
    """price → float, availability → int, reviews → int, rating → int, даты не требуются."""

    def process_item(self, item, spider):
        try:
            # Цена: "£51.77" → 51.77
            price_raw = item.get("price_excl_tax", "")
            price_match = re.search(r"[\d.]+", price_raw.replace(",", ""))
            if not price_match:
                raise ValueError(f"Bad price: {price_raw!r}")
            item["price_excl_tax"] = float(price_match.group())

            # Наличие: "In stock (22 available)" → 22
            avail_raw = item.get("availability", "")
            avail_match = re.search(r"(\d+)", avail_raw)
            if not avail_match:
                raise ValueError(f"Bad availability: {avail_raw!r}")
            item["availability"] = int(avail_match.group(1))

            # Число отзывов: "0" → 0
            reviews_raw = str(item.get("number_of_reviews", "")).strip()
            if not reviews_raw.isdigit():
                raise ValueError(f"Bad reviews: {reviews_raw!r}")
            item["number_of_reviews"] = int(reviews_raw)

            # Рейтинг: "star-rating Three" → 3
            rating_map = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}
            rating_raw = item.get("rating", "")
            for word, num in rating_map.items():
                if word in rating_raw:
                    item["rating"] = num
                    break
            else:
                item["rating"] = 0  # не критично, но не падаем

            # Обрезка пробелов и нормализация регистра для текстовых полей
            for field in ("title", "category", "description", "upc"):
                if item.get(field):
                    item[field] = item[field].strip()

        except (ValueError, AttributeError) as e:
            spider.crawler.stats.inc_value("dropped/cleaning_error")
            raise DropItem(f"Cleaning error: {e}; UPC={item.get('upc')}")

        return item

class DuplicatesPipeline:
    """Дедупликация по UPC (бизнес-ключ), не по URL."""

    def __init__(self):
        self.seen = set()

    def open_spider(self, spider):
        self.seen = set()

    def process_item(self, item, spider):
        key = item.get("upc")
        if not key:
            spider.crawler.stats.inc_value("dropped/missing_business_key")
            raise DropItem("No UPC")
        if key in self.seen:
            spider.crawler.stats.inc_value("duplicates/upc")
            raise DropItem(f"Duplicate UPC: {key}")
        self.seen.add(key)
        return item

    def close_spider(self, spider):
        spider.crawler.stats.set_value("duplicates/unique_keys", len(self.seen))

class SQLitePipeline:
    """Соединение в open_spider/close_spider; запись пакетами через executemany;
    INSERT OR REPLACE по UPC (UPSERT)."""

    BATCH_SIZE = 50

    def open_spider(self, spider):
        self.conn = sqlite3.connect("data/crawl.db")
        self.cur = self.conn.cursor()
        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS books (
                upc TEXT PRIMARY KEY,
                title TEXT,
                category TEXT,
                price_excl_tax REAL,
                availability INTEGER,
                number_of_reviews INTEGER,
                description TEXT,
                rating INTEGER,
                product_url TEXT,
                image_url TEXT
            )
        """)
        self.conn.commit()
        self.batch = []

    def process_item(self, item, spider):
        self.batch.append((
            item["upc"], item["title"], item["category"],
            item["price_excl_tax"], item["availability"],
            item["number_of_reviews"], item["description"],
            item.get("rating", 0), item.get("product_url", ""),
            item.get("image_url", ""),
        ))
        if len(self.batch) >= self.BATCH_SIZE:
            self._flush(spider)
        return item

    def _flush(self, spider):
        if not self.batch:
            return
        self.cur.executemany("""
            INSERT OR REPLACE INTO books
            (upc, title, category, price_excl_tax, availability,
             number_of_reviews, description, rating, product_url, image_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, self.batch)
        self.conn.commit()
        spider.crawler.stats.inc_value("db/rows_written", len(self.batch))
        self.batch.clear()

    def close_spider(self, spider):
        self._flush(spider)
        self.cur.close()
        self.conn.close()