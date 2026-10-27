import requests
import csv
import time

def collect_quotes_api(max_pages: int = 25):
    records = []
    log = []

    for page_num in range(1, max_pages + 1):
        url = f"https://quotes.toscrape.com/api/quotes?page={page_num}"
        start = time.perf_counter()

        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            print(f"Ошибка на странице {page_num}: {e}")
            break

        quotes = data.get("quotes", [])
        for q in quotes:
            records.append({
                "text": q.get("text", "").strip(),
                "author": q.get("author", {}).get("name", "").strip()
                          if isinstance(q.get("author"), dict)
                          else q.get("author", "").strip(),
                "tags": "|".join(q.get("tags", [])),
            })

        log.append({
            "page": page_num,
            "records_on_page": len(quotes),
            "total": len(records),
            "duration_sec": round(time.perf_counter() - start, 3),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        })

        print(f"Итерация {page_num}: страница {url} — элементов {len(quotes)}, всего {len(records)}")

        if not data.get("has_next", False):
            break

        time.sleep(0.5)

    return records, log


if __name__ == "__main__":
    start = time.time()
    records, log = collect_quotes_api(max_pages=25)
    print('Прошло', round(time.time() - start, 4), 'секунд.')

    with open("data_light.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["text", "author", "tags"])
        writer.writeheader()
        writer.writerows(records)

    with open("collection_log_api.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["page", "records_on_page", "total", "duration_sec", "timestamp"],
        )
        writer.writeheader()
        writer.writerows(log)

    print(f"Собрано {len(records)} записей. Сохранено в data_light.csv")
    print(f"Журнал сохранён в collection_log_api.csv")
    