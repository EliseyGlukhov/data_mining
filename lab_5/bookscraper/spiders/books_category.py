# bookscraper/spiders/books_category.py
import scrapy
from bookscraper.items import BookItem

class BooksCategorySpider(scrapy.Spider):
    name = "books_category"
    allowed_domains = ["books.toscrape.com"]
    start_urls = ["https://books.toscrape.com/"]

    # ---------- УРОВЕНЬ 1: главная → категории ----------
    def parse(self, response):
        """
        Извлекаем ссылки на категории из бокового меню.
        Селектор: div.side_categories ul li a — стабильный семантический класс.
        """
        for cat_link in response.css("div.side_categories ul li a"):
            category_name = cat_link.css("::text").get(default="").strip()
            category_url = response.urljoin(cat_link.attrib["href"])
            yield scrapy.Request(
                category_url,
                callback=self.parse_category,
                cb_kwargs={"category": category_name},
                errback=self.errback_category,
            )
    
    # ---------- УРОВЕНЬ 1.5: пагинация внутри категории ----------
    def parse_category(self, response, category):
        """
        Разбираем страницу списка книг внутри категории.
        Для каждой карточки — запрос на уровень 2 с передачей category через cb_kwargs.
        """
        for article in response.css("article.product_pod"):
            book_url = article.css("h3 a::attr(href)").get()
            if not book_url:
                continue  # защита от нетипичной карточки
            yield response.follow(
                book_url,
                callback=self.parse_item,
                cb_kwargs={"category": category},   # контекст уровня 1
                errback=self.errback_item,
            )

        # Пагинация: li.next a — стабильный селектор
        next_page = response.css("li.next a::attr(href)").get()
        if next_page:
            yield response.follow(
                next_page,
                callback=self.parse_category,
                cb_kwargs={"category": category},   # контекст сохраняется
            )

    # ---------- УРОВЕНЬ 2: карточка книги ----------
    def parse_item(self, response, category):
        """
        Извлекаем детальные поля с карточки.
        Все обращения — через .get() с fallback, чтобы не падать на неполной карточке.
        """
        item = BookItem()

        # UPC — из таблицы product information (стабильный th/td)
        item["upc"] = response.css(
            "table.table-striped tr:contains('UPC') td::text"
        ).get(default="").strip()

        # Цена без налога
        price_excl = response.css(
            "table.table-striped tr:contains('Price (excl. tax)') td::text"
        ).get(default="").strip()
        item["price_excl_tax"] = price_excl  # очистка будет в пайплайне

        # Наличие — "In stock (22 available)"
        availability_text = response.css(
            "table.table-striped tr:contains('Availability') td::text"
        ).get(default="").strip()
        item["availability"] = availability_text

        # Число отзывов
        reviews_text = response.css(
            "table.table-striped tr:contains('Number of reviews') td::text"
        ).get(default="").strip()
        item["number_of_reviews"] = reviews_text

        # Описание — может отсутствовать
        item["description"] = response.css(
            "#product_description ~ p::text"
        ).get(default="").strip()

        # Название
        item["title"] = response.css("h1::text").get(default="").strip()

        # Категория — из cb_kwargs (уровень 1)
        item["category"] = category

        # Рейтинг — из класса star-rating Three / Four / Five
        rating_class = response.css("p.star-rating::attr(class)").get(default="")
        item["rating"] = rating_class  # типизация в пайплайне

        # URL и изображение — для трассировки
        item["product_url"] = response.url
        item["image_url"] = response.css("img::attr(src)").get(default="")

        yield item

    # ---------- ERRBACK ----------
    def errback_category(self, failure):
        self.crawler.stats.inc_value("errback/category")
        self.logger.error("Category request failed: %s", failure.request.url)

    def errback_item(self, failure):
        self.crawler.stats.inc_value("errback/item")
        self.logger.error("Item request failed: %s", failure.request.url)

    # ---------- ЗАКРЫТИЕ: сохранение статистики ----------
    def closed(self, reason):
        stats = self.crawler.stats.get_stats()
        with open(f"data/stats_{self.name}.json", "w", encoding="utf-8") as f:
            import json
            json.dump(stats, f, ensure_ascii=False, indent=2, default=str)