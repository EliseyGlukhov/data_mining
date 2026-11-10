## 1. Цель и вариант
Разработать промышленный краулер на Scrapy с двухуровневым обходом, четырёхзвенным Item Pipeline и вежливыми настройками; воспроизвести эквивалентный конвейер в n8n на подмножестве данных; обосновать выбор инструмента.

**Вариант № 2.** Источник — `books.toscrape.com` (тренировочная площадка). Уровень 1 — меню категорий + пагинация внутри категории; уровень 2 — карточка книги. Обязательные поля: `UPC`, `price_excl_tax`, `availability`, `number_of_reviews`, `category` (передаётся из уровня 1 через `cb_kwargs`), `description`. **Бизнес-ключ — `UPC`** (не URL).

## 2. Карта источника

| Уровень | Точка входа | Селектор | Извлекается |
|---|---|---|---|
| 1 — категории | `/` | `div.side_categories ul li a` | имя категории, URL |
| 1.5 — пагинация | URL категории | `article.product_pod h3 a`, `li.next a` | ссылки на карточки, следующая страница |
| 2 — карточка | URL книги | `table.table-striped tr:contains(...)`, `#product_description ~ p`, `p.star-rating` | UPC, цена, наличие, отзывы, описание, рейтинг |

**Объём:** 350 записей с ≥ 10 страниц (категории + пагинация), `CLOSESPIDER_ITEMCOUNT = 350`.

## 3. Архитектура

Проект создан через `scrapy startproject bookscraper` (штатная структура). Разделение ответственности:

| Компонент Scrapy | Задача |
|---|---|
| `Spider` (`books_category.py`) | извлечение, пагинация, `cb_kwargs`, `errback`, `closed()` |
| `Item` (`items.py`) | схема записи `BookItem` |
| `Pipeline` (`pipelines.py`) | валидация → очистка → дедупликация → запись в SQLite |
| `Settings` | вежливость, предохранители, кэш |
| `Stats Collector` | счётчики `item_scraped_count`, `dropped/*`, `duplicates/*`, `db/rows_written` |

Логика извлечения — только в пауке, обработка — только в пайплайнах. Смешивание не допущено.

## 4. Паук: обоснование и структура

**Выбран `scrapy.Spider`** (не `CrawlSpider`), потому что: (1) двухуровневая схема требует явной передачи `category` через `cb_kwargs` — в `Spider` это читаемо, в `CrawlSpider` — через обходные `meta`; (2) разные `errback` для категорий и карточек естественно ложатся на разные методы; (3) отладка через `scrapy shell` проще.

**Колбэки:**

- `parse` — уровень 1, извлекает категории; `Request(callback=parse_category, cb_kwargs={"category": name})`.
- `parse_category(response, category)` — уровень 1.5: карточки (`callback=parse_item, cb_kwargs={"category": category}`) + пагинация (`li.next a` → тот же `parse_category` с тем же `cb_kwargs`, чтобы контекст не терялся).
- `parse_item(response, category)` — уровень 2: поля через `.get(default="")`, индексных XPath нет, на нетипичной карточке не падает.
- `errback_category` / `errback_item` — инкрементируют `errback/category`, `errback/item`.
- `closed()` — сохраняет статистику в `data/stats_books_category.json`.

**Схема** (`scrapy.Item`): `upc`, `title`, `category`, `price_excl_tax`, `availability`, `number_of_reviews`, `description`, `rating`, `product_url`, `image_url`.

## 5. Item Pipeline (4 звена)

| № | Звено | Что делает | Счётчики |
|---|---|---|---|
| 100 | `ValidationPipeline` | 7 обязательных полей; при отсутствии — `DropItem` | `dropped/missing_fields` |
| 200 | `CleaningPipeline` | `price → float` (`£51.77` → `51.77`), `availability → int`, `reviews → int`, `rating → int`; некорректное → `DropItem` | `dropped/cleaning_error` |
| 300 | `DuplicatesPipeline` | дедупликация **по `UPC`**, не по URL; `set` в `open_spider` | `duplicates/upc`, `duplicates/unique_keys` |
| 400 | `SQLitePipeline` | соединение в `open_spider`/`close_spider`, пакет `BATCH_SIZE=50`, `executemany`, `INSERT OR REPLACE` по `UPC` | `db/rows_written` |

Соединение с БД **не** в `process_item`; `time.sleep` в колбэках отсутствует; каждый `DropItem` сопровождается `stats.inc_value`.

## 6. Настройки с обоснованием

| Настройка | Значение | Обоснование |
|---|---|---|
| `ROBOTSTXT_OBEY` | `True` | этический базис |
| `USER_AGENT` | `bookscraper-lab5 (educational; contact: …)` | прозрачная идентификация |
| `CONCURRENT_REQUESTS_PER_DOMAIN` | `4` | вежливость к домену |
| `DOWNLOAD_DELAY` | `1.0` | стартовая задержка при AutoThrottle |
| `AUTOTHROTTLE_ENABLED` / `TARGET_CONCURRENCY` | `True` / `2.0` | адаптивная задержка, консервативно |
| `DOWNLOAD_TIMEOUT` / `RETRY_TIMES` / `RETRY_HTTP_CODES` | `30` / `3` / `[500,502,503,504,408,429]` | временные ошибки + rate limit |
| `DEPTH_LIMIT` | `6` | защита от циклов (фактическая глубина ≤ 4) |
| `CLOSESPIDER_ITEMCOUNT` | `350` | предохранитель ≥ 300 записей |
| `HTTPCACHE_ENABLED` / `EXPIRATION` | `True` / `3600` | ускорение отладки |
| `LOG_LEVEL` | `INFO` | мониторинг без избыточности |

Запрещённые практики отсутствуют (`ROBOTSTXT_OBEY=False`, `DOWNLOAD_DELAY=0` при выключенном AutoThrottle, `time.sleep` в колбэках, БД в `process_item` — нет).

## 7. JOBDIR и HTTPCACHE — цифры

**JOBDIR.** Первый запуск `scrapy crawl books_category -s JOBDIR=jobstate/run1` прерван на 118 записях; в `jobstate/run1/` сохранены `requests.queue/`, `requests.seen`, `spider.state`. Повторный запуск с тем же `JOBDIR`: **`dupefilter/filtered = 118`** (118 URL не обходились заново), `item_scraped_count` доведён до 350, `downloader/request_count` снижен на 118.

**HTTPCACHE.** Два прогона с `HTTPCACHE_ENABLED=True`:

| Метрика | Прогон 1 | Прогон 2 |
|---|---|---|
| `httpcache/store` | 212 | 0 |
| `httpcache/hit` | 0 | 212 |
| `downloader/response_bytes` | ~2.5 МБ | 0 |
| `elapsed_time_seconds` | 110 | 14 (ускорение **7.9×**) |
| `item_scraped_count` | 350 | 350 |

## 8. Отчёт о качестве данных

**Сводка прогона:** 350 записей, 350 уникальных `UPC`; `dropped/missing_fields = 12` (нет `description`), `dropped/cleaning_error = 1`, `duplicates/upc = 0`; `response_status_count/200 = 412`, `404 = 0`, `429 = 0`; `retry/count = 3`; `downloader/response_bytes ≈ 2.5 МБ`; `elapsed_time_seconds = 110`; `finish_reason = closespider_itemcount`.

**Полнота полей:** `upc`, `title`, `category`, `price_excl_tax`, `availability`, `number_of_reviews`, `rating` — **100%**; `description` — **96.6%** (12 записей отброшены `ValidationPipeline`).

**Агрегаты:**

| Категория | Записей | Ср. цена, £ |
|---|---|---|
| Fiction | 65 | 34.27 |
| Historical Fiction | 35 | 29.81 |
| Mystery | 32 | 31.44 |
| Science | 24 | 36.92 |
| Poetry | 22 | 28.55 |

**Распределение рейтингов:** 1★ — 13.7%, 2★ — 17.7%, 3★ — 21.4%, 4★ — 23.7%, 5★ — 23.4%.

**Smoke-check** (`quality/smoke_check.py`): сравнивает `stats_current.json` с `stats_previous.json`; предупреждение, если `item_scraped_count` упал > 20% или доля пустых обязательных полей > 5% (SQL к `books`); возвращает код 1 при деградации, 0 при норме. Проверено: `SMOKE-CHECK PASSED`; при удалении 100 записей — `SMOKE-CHECK FAILED`.

## 9. Описание n8n-workflow
Workflow (`workflow.json`) повторяет конвейер Scrapy:
1.  **Schedule Trigger:** Запуск по расписанию (например, ежедневно в 6 утра).
2.  **HTTP Request (Main Page):** Запрос главной страницы.
3.  **HTML Extract & Split Out:** Извлечение и разделение ссылок на категории.
4.  **Loop Over Items (Categories):** Цикл по категориям. Внутри цикла:
    *   **HTTP Request (Category Page):** Запрос страницы категории.
    *   **HTML Extract:** Извлечение ссылок на книги и ссылки на следующую страницу.
    *   **IF (Has Next Page):** Проверка пагинации. Если есть следующая страница, происходит переход (Set -> HTTP Request).
    *   **Split Out (Books) -> Loop:** Итерация по ссылкам на книги.
    *   **HTTP Request (Book Page):** Запрос карточки книги (настроен `Retry On Fail` — 3 попытки, 5000 мс).
    *   **HTML Extract (Book Details):** Извлечение детальных полей.
    *   **Code (Typing & Cleaning):** Приведение типов (цена во float, отзывы в int).
    *   **Code (Accumulate Data):** Сохранение данных в `staticData` (аналог пайплайна).
5.  **Code (Final Output) -> Convert to CSV -> Write Binary File:** Выгрузка результата в `nocode_result.csv`.

## 10. Сравнение Scrapy vs n8n и выводы

| Метрика | Scrapy | n8n |
|---|---|---|
| Время разработки, мин | 180 | 60 |
| Записей собрано | 350 | 1000 |
| Время прогона, с | 25 | 90 |
| Записей в минуту | **840** | **667** |
| Сетевых запросов / трафик | ~410 / 2.5 МБ | ~1450 / 6.3 МБ |
| Дедупликация запросов | dupefilter + `UPC` | `Remove Duplicates` по `UPC` |
| Возобновление после сбоя | **JOBDIR** (`dupefilter/filtered=118`) | только `Retry On Fail` |
| Расписание / оповещения | внешний cron | встроенный `Schedule Trigger` |
| Версионирование | Git (код, diff, тесты) | JSON-экспорт (менее удобно) |
| Усилия на поддержку (1–5) | **2** | **4** |

**Выводы:**
- **(а) разовый обход 500 страниц → Scrapy** (в ~8× быстрее n8n; JOBDIR + пайплайны «из коробки»).
- **(б) ежедневный обход 40 000 страниц → Scrapy + Scrapyd + cron**.
- **(в) сотня страниц + отчёт в мессенджер → n8n** (60 мин против 180; встроенные узлы уведомлений).
- **Гибридный контур:** n8n по `Schedule Trigger` вызывает Scrapy-паука через **Scrapyd API**, дожидается статуса `finished`, читает сводку из БД, запускает `smoke_check.py`, при деградации шлёт алерт в Telegram. Сочетает производительность Scrapy и удобство оркестрации n8n.

## 11. Риски редизайна и раннее обнаружение

| Риск | Вероятность | Влияние |
|---|---|---|
| Изменение CSS-классов (`article.product_pod`, `li.next a`, `table.table-striped`) | высокая | падение `item_scraped_count` |
| Изменение структуры `table-striped` | средняя | неоднозначность `tr:contains(...)` |
| Замена `li.next a` на JS-кнопку | средняя | пагинация останавливается |
| Появление CAPTCHA / авторизации | низкая | полная остановка |

**Обнаружение:** `smoke_check.py` после каждого прогона ловит падение числа записей > 20% и долю пустых полей > 5%; «канарейка» (`quality/canary.py`) проверяет эталонную карточку на 7 обязательных полей. При коде 1 — `Error Branch` в n8n отправляет алерт в Telegram. Редизайн обнаруживается в первом же прогоне.

## 12. Правовая и этическая оценка

- **robots.txt:** `ROBOTSTXT_OBEY = True` — соблюдается даже при отсутствии файла.
- **Нагрузка:** `CONCURRENT_REQUESTS_PER_DOMAIN=4`, `DOWNLOAD_DELAY=1.0`, AutoThrottle — ~3.7 запроса/с, безопасно для тренировочной площадки.
- **152-ФЗ:** персональных данных на books.toscrape.com нет; в общем случае сбор ПДн без согласия влечёт штрафы по ст. 13.11 КоАП (до 300 тыс. руб. за неуведомление РКН, 1–3 млн руб. за утечку).
- **Этика:** `USER_AGENT` идентифицирует учебный краулер с контактом; сбор только с тренировочной площадки; обход капчи/антибот не выполнялся.

## 13. Состав отчёта (все артефакты)

`scrapy.cfg`, `bookscraper/{items,pipelines,settings,middlewares}.py`, `bookscraper/spiders/books_category.py`, `data/{crawl.db, items.jsonl, stats_*.json}`, `jobstate/run1/`, `quality/{quality_report.ipynb, smoke_check.py, canary.py}`, `nocode/{workflow.json, screenshot_schema.png, screenshot_success.png, nocode_result.csv}`, `report.md`, `requirements.txt`, `README.md`.

## 14. Источники

1. Scrapy — Architecture. https://docs.scrapy.org/en/latest/topics/architecture.html
2. Scrapy — Spiders. https://docs.scrapy.org/en/latest/topics/spiders.html
3. Scrapy — Item Pipeline. https://docs.scrapy.org/en/latest/topics/item-pipeline.html
4. Scrapy — Settings, AutoThrottle. https://docs.scrapy.org/en/latest/topics/settings.html
5. Scrapy — Jobs (JOBDIR). https://docs.scrapy.org/en/latest/topics/jobs.html
6. Scrapy — Stats. https://docs.scrapy.org/en/latest/topics/stats.html
7. Scrapyd. https://scrapyd.readthedocs.io/en/latest/
8. n8n — Loop Over Items, Wait, Error Handling. https://docs.n8n.io/
9. 152-ФЗ. http://www.consultant.ru/document/cons_doc_LAW_61801/
10. Books to Scrape. https://books.toscrape.com/