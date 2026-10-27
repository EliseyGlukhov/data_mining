# Отчёт по лабораторной работе № 3
## Сбор данных через REST API: код и no-code

**Вариант:** 2 — GitHub REST: issues репозитория (Link-пагинация); обогащение — GitHub: репозиторий и контрибьюторы.  
**Целевая задача анализа:** динамика открытия/закрытия issue, время жизни задачи.  
**Студент:** _Глухов Елисей Александрович_  
**Репозиторий для сбора:** `pandas-dev/pandas`

---

## 1. Цель и вариант

Цель работы — реализовать воспроизводимый сбор данных через REST API двумя способами: программно на Python и в no-code среде n8n, — а затем сравнить подходы по измеренным характеристикам.

В рамках варианта 2 собраны issue репозитория `pandas-dev/pandas` через GitHub REST API с пагинацией по заголовку `Link`. Дополнительно выполнено обогащение метаданными репозитория: язык, число звёзд, форков, открытых issue, дата создания. Итоговая таблица предназначена для анализа динамики открытия/закрытия issue и среднего времени жизни задачи.

Объём сбора: **500 сырых записей**, **5 страниц** пагинации, после нормализации — **362 строки** (issue, у которых есть хотя бы одна метка). Требование «≥ 300 записей и ≥ 3 страниц» выполнено.

---

## 2. Паспорт API

| Поле | Значение |
|---|---|
| Название и базовый URL | GitHub REST API, `https://api.github.com` |
| Версия и способ её указания | `2022-11-28`, заголовок `X-GitHub-Api-Version` |
| Используемые эндпоинты | `GET /repos/{owner}/{repo}/issues` — основной сбор; `GET /repos/{owner}/{repo}` — обогащение метаданными репозитория; при необходимости `GET /repos/{owner}/{repo}/contributors` — контрибьюторы |
| Аутентификация | Personal Access Token через переменную окружения `GITHUB_TOKEN`; в коде и отчёте не хранится |
| Тип пагинации и параметры | Пагинация через заголовок `Link` (`rel="next"`); параметры `state=all`, `per_page=100`, `sort=created`, `direction=asc` |
| Документированные лимиты | 60 запросов/час без токена, 5 000 запросов/час с токеном; вторичные лимиты GitHub |
| Заголовки лимитов в ответе | `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`, `Retry-After` |
| Формат дат | ISO 8601, UTC, например `2010-09-29T19:45:47Z` |
| Ключ уникальности записи | `issue.id` (внутри репозитория также `issue.number`) |
| Наличие персональных данных | Публичные логины авторов, назначенных, ссылки на профили; email, телефоны, реальные имена не собираются |
| Ограничения условий использования | Соблюдение GitHub Terms of Service, Acceptable Use, лимитов API; запрещён обход лимитов и избыточная нагрузка |

---

## 3. Архитектура пайплайна

```text
GitHub REST API
   │  GET /repos/pandas-dev/pandas/issues?state=all&per_page=100&page=N
   │  Link-пагинация, retry 429/5xx, пауза 1 с
   ▼
requests.Session + safe_get_json
   │  проверка статуса, Content-Type, первых 200 байт ошибки
   ▼
data_raw.jsonl  +  collection_log.csv
   │  сырые ответы построчно; журнал: page, url, params, status_code,
   │  records_count, duration_sec, timestamp, rate_limit_remaining/reset
   ▼
pandas.json_normalize
   │  record_path="labels", meta=[issue.*], sep="."
   │  развёртывание массива labels; assignees — отдельная нормализация
   ▼
Обогащение
   │  GET /repos/pandas-dev/pandas → repo_language, repo_stars,
   │  repo_forks, repo_open_issues, repo_created_at
   │  число строк до/после: 362 → 362
   ▼
Проверка качества
   │  полнота полей, дубликаты по issue_id, типизация datetime UTC,
   │  бизнес-проверки: closed_at ≥ created_at, comments ≥ 0
   ▼
data_clean.csv  +  state.json
```

## 4. Результаты проверки качества данных

**Полнота полей после нормализации:**

| Поле | Полнота, % |
|---|---:|
| `issue_id` | 100.0 |
| `labels` | 100.0 |
| `issue_number` | 100.0 |
| `issue_title` | 100.0 |
| `issue_state` | 100.0 |
| `issue_created_at` | 100.0 |
| `issue_closed_at` | 100.0 |
| `issue_updated_at` | 100.0 |
| `issue_comments` | 100.0 |
| `issue_author_association` | 100.0 |
| `issue_html_url` | 100.0 |
| `issue_body` | 99.17 |
| `issue__collected_at` | 100.0 |
| `assignees_logins` | 0.55 |
| `repo_full_name` | 100.0 |
| `repo_language` | 100.0 |
| `repo_stars` | 100.0 |
| `repo_forks` | 100.0 |
| `repo_open_issues` | 100.0 |
| `repo_created_at` | 100.0 |

**Дубликаты и бизнес-проверки:**

- дубликаты по ключу `issue_id`: **0**;
- `closed_at ≥ created_at` для всех закрытых issue: **true**;
- `issue_comments ≥ 0`: **true**;
- даты приведены к `datetime` с UTC;
- вычислено поле `lifetime_days` — время жизни issue в днях;
- поле `assignees_logins` заполнено только у 0.55% записей, что объясняется редким назначением исполнителей в ранних issue; для анализа динамики это поле не является критичным.

**Инкрементальность:** в `state.json` сохраняется «водяной знак» — максимальный `issue_created_at`. При повторном запуске фильтр `issue_created_at > watermark` отбрасывает уже собранные записи; новые записи либо отсутствуют, либо добавляются только действительно новые. Дублирования в `data_clean.csv` нет.

---

## 5. No-code сценарий (n8n)

Реализован упрощённый сценарий в n8n:

1. **Schedule Trigger** — ежедневный запуск в 09:00 (или ручной запуск).
2. **HTTP Request** — `GET https://api.github.com/repos/pandas-dev/pandas/issues` с параметрами `state=all`, `per_page=100`, `page=1`; заголовки `Accept: application/vnd.github+json`, `User-Agent`, `X-GitHub-Api-Version: 2022-11-28`; токен — через Credential, не в узле.
3. **Пагинация** — в узле HTTP Request включена обработка `Link` либо используется `Loop Over Items` + `Wait` 1 с; ограничение — 5 страниц.
4. **Split Out** — массив issue разворачивается в отдельные элементы.
5. **Edit Fields** — минимум три преобразования:
   - переименование `id` → `issue_id`, `title` → `issue_title`;
   - приведение `created_at` к типу Date;
   - вычисляемое поле `is_open = state == "open"`;
   - при наличии `closed_at` — вычисление `lifetime_days`.
6. **Google Sheets / CSV** — добавление строк в таблицу `nocode_result.csv` / Google Sheets.
7. **Error branch** — `IF` по коду ответа ≥ 400: уведомление в Slack/email и запись в лог-лист.

**Результат no-code прогона:** собрано **500 записей** (5 страниц, 100 строк), выгружено в Google Sheets/CSV; скриншоты workflow и успешного выполнения приложены в папке `nocode/`. 

---

## 6. Сравнение подходов

| Критерий | Python | n8n |
|---|---:|---:|
| Время разработки, мин | 120 | 50 |
| Число собранных записей | 500 сырых / 362 нормализованных | 500 |
| Время выполнения одного прогона, с | 40 | 20 |
| Поддержка пагинации | Полная: разбор `Link`, остановка по `next`/пустой странице | Полная: Pagination в HTTP Request или Loop Over Items + Wait |
| Обработка ошибок и повторов | Retry только для 429/5xx, backoff + jitter, `Retry-After`, таймауты | Базовая: Error branch, Wait, повторный запуск; экспоненциальный backoff — вручную |
| Воспроизводимость | Git, `requirements.txt`, `state.json`, README | Экспорт `workflow.json` |
| Стоимость при 100 прогонах в месяц | бесплатно (локально, GitHub token бесплатный) | бесплатно при развёртывании на своём ПК; |
| Порог входа (1–5) | 4 | 2 |

**Вывод.** Для задачи варианта 2 Python оправдан там, где нужны строгий контроль пагинации, воспроизводимость, инкрементальность и обработка ошибок: это основной пайплайн, который можно версионировать и перезапускать. n8n удобен для быстрого прототипа, регулярного запуска и выгрузки в Google Sheets; однако при больших объёмах и сложных правилах retry он уступает Python. Гибридный вариант для заказчика: n8n — как оркестратор расписания и уведомлений, Python-скрипт — как исполнитель сбора, нормализации и проверки качества; результат — общая таблица или БД.

---

## 7. Правовая и этическая оценка

- Используется публичный GitHub REST API в соответствии с GitHub Terms of Service и Acceptable Use; соблюдаются лимиты, `User-Agent`, паузы между запросами.
- Персональные данные: собираются только общедоступные идентификаторы (`login`), ссылки на профили и публичные метаданные issue. Email, телефоны, реальные имена, платёжные и иные чувствительные данные не собираются.
- Основание обработки по 152-ФЗ: данные общедоступны, обрабатываются в учебных целях, без профилирования и автоматизированных решений, затрагивающих права субъектов; используется минимизация состава данных.
- Срок хранения: локально — до защиты лабораторной работы, далее файлы удаляются; передача третьим лицам не осуществляется.
- Этика: не создаётся избыточная нагрузка на API, не обходятся лимиты, не собираются данные из закрытых репозиториев.

---

## 8. Источники

1. GitHub REST API — Issues: https://docs.github.com/en/rest/issues/issues
2. GitHub REST API — Repositories: https://docs.github.com/en/rest/repos/repos
3. GitHub REST API — Pagination: https://docs.github.com/en/rest/using-the-rest-api/using-pagination-in-the-rest-api
4. GitHub REST API — Rate limits: https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api
5. pandas.json_normalize: https://pandas.pydata.org/docs/reference/api/pandas.json_normalize.html
6. Requests: Advanced Usage: https://requests.readthedocs.io/en/latest/user/advanced/
7. n8n HTTP Request: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.httprequest/
8. 152-ФЗ «О персональных данных»: http://www.consultant.ru/document/cons_doc_LAW_61801/
9. RFC 9110 — HTTP Semantics: https://www.rfc-editor.org/rfc/rfc9110.html
10. RFC 8259 — JSON: https://www.rfc-editor.org/rfc/rfc8259.html