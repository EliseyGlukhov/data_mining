ITEM_PIPELINES = {
    "bookscraper.pipelines.ValidationPipeline": 100,
    "bookscraper.pipelines.CleaningPipeline": 200,
    "bookscraper.pipelines.DuplicatesPipeline": 300,
    "bookscraper.pipelines.SQLitePipeline": 400,
}

BOT_NAME = "bookscraper"
SPIDER_MODULES = ["bookscraper.spiders"]
NEWSPIDER_MODULE = "bookscraper.spiders"

# --- Вежливость ---
ROBOTSTXT_OBEY = True
# Обоснование: этический базис; books.toscrape.com не имеет robots.txt,
# но правило соблюдается — это часть учебной культуры скрапинга.

USER_AGENT = "bookscraper-lab5 (educational project; contact: student@example.edu)"
# Обоснование: прозрачная идентификация учебного краулера.

CONCURRENT_REQUESTS = 16
CONCURRENT_REQUESTS_PER_DOMAIN = 4
# Обоснование: ≤4 запросов к домену — умеренная нагрузка на учебный сайт.

DOWNLOAD_DELAY = 1.0
# Обоснование: 1 секунда между запросами к одному домену; при AutoThrottle
# это стартовая задержка, которая адаптируется автоматически.

AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 1.0
AUTOTHROTTLE_MAX_DELAY = 10.0
AUTOTHROTTLE_TARGET_CONCURRENCY = 2.0
# Обоснование: AutoThrottle подстраивает задержку под ответы сервера;
# target concurrency 2.0 — консервативно и вежливо.

DOWNLOAD_TIMEOUT = 30
RETRY_TIMES = 3
RETRY_HTTP_CODES = [500, 502, 503, 504, 408, 429]
# Обоснование: стандартные временные ошибки; 429 — rate limiting.

# --- Предохранители ---
DEPTH_LIMIT = 6
# Обоснование: главная → категория → пагинация → карточка = глубина ≤ 4;
# 6 — запас, защита от случайных циклов.

CLOSESPIDER_ITEMCOUNT = 350
# Обоснование: требование ≥300 записей; 350 даёт запас и останавливает
# прогон, не дожидаясь исчерпания всего каталога (1000 книг).

# --- Кэш для отладки ---
HTTPCACHE_ENABLED = True
HTTPCACHE_EXPIRATION_SECS = 3600
HTTPCACHE_DIR = "httpcache"
# Обоснование: при повторных прогонах во время отладки ответы берутся
# из кэша, что ускоряет итерации и снижает нагрузку на сайт.

# --- Логирование ---
LOG_LEVEL = "INFO"
# Обоснование: достаточный уровень для мониторинга без избыточности.

# --- Feed export (опционально) ---
FEED_EXPORT_ENCODING = "utf-8"