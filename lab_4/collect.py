import asyncio
import csv
import sys
import time
from pathlib import Path

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

ARTIFACTS = Path("artifacts")
ARTIFACTS.mkdir(exist_ok=True)

BLOCKED_RESOURCES = {"image", "media", "font", "stylesheet"}
START_URL = "https://quotes.toscrape.com/js/"


async def block_resources(route):
    if route.request.resource_type in BLOCKED_RESOURCES:
        await route.abort()
    else:
        await route.continue_()


async def collect_quotes_browser(max_iterations):
    records = []
    log_rows = []
    seen = set()
    no_growth_streak = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )
        context.set_default_timeout(15000)
        context.set_default_navigation_timeout(30000)

        page = await context.new_page()
        await page.route("**/*", block_resources)

        try:
            await page.goto(START_URL, wait_until="domcontentloaded")

            await page.wait_for_selector("div.quote", state="visible", timeout=15000)
        except PlaywrightTimeoutError as e:
            print(f"Не удалось загрузить стартовую страницу: {e}")
            await page.screenshot(path=ARTIFACTS / "fail_start.png")
            (ARTIFACTS / "fail_start.html").write_text(
                await page.content(), encoding="utf-8"
            )
            await context.close()
            await browser.close()
            return records, log_rows

        iteration = 0
        while iteration < max_iterations:
            iteration += 1
            start = time.perf_counter()

            quotes_data = await page.eval_on_selector_all(
                "div.quote",
                """(els) => els.map(el => ({
                    text: el.querySelector('span.text')?.innerText?.trim() ?? '',
                    author: el.querySelector('small.author')?.innerText?.trim() ?? '',
                    tags: Array.from(el.querySelectorAll('a.tag'))
                              .map(t => t.innerText.trim()).sort().join('|'),
                }))""",
            )

            added = 0
            for q in quotes_data:
                key = (q["text"], q["author"])
                if key not in seen:
                    seen.add(key)
                    records.append(q)
                    added += 1

            duration = time.perf_counter() - start
            log_rows.append({
                "iteration": iteration,
                "elements_on_page": len(quotes_data),
                "new_records": added,
                "total": len(records),
                "duration_sec": round(duration, 3),
                "url": page.url,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            })
            print(f"Итерация {iteration}: страница {page.url} — элементов {len(quotes_data)}, всего {len(records)}")

            if added == 0:
                no_growth_streak += 1
                if no_growth_streak >= 3:
                    print(f"Остановка: {no_growth_streak} итерации подряд без прироста.")
                    break
            else:
                no_growth_streak = 0

            next_link = page.locator("li.next > a")
            if await next_link.count() == 0:
                print("Кнопка Next отсутствует — достигнута последняя страница.")
                break

            current_url = page.url
            try:
                async with page.expect_navigation(
                    wait_until="domcontentloaded", timeout=15000
                ):
                    await next_link.click()


                await page.wait_for_url(
                    lambda url: url != current_url,
                    timeout=10000,
                )

                await page.wait_for_selector(
                    "div.quote", state="visible", timeout=15000
                )
            except PlaywrightTimeoutError as e:
                print(f"Таймаут при переходе на следующую страницу: {e}")
                await page.screenshot(path=ARTIFACTS / f"timeout_iter_{iteration}.png")
                (ARTIFACTS / f"timeout_iter_{iteration}.html").write_text(
                    await page.content(), encoding="utf-8"
                )
                break

            await asyncio.sleep(0.5)

        try:
            await page.screenshot(path=ARTIFACTS / "final_page.png", full_page=True)
            (ARTIFACTS / "final_page.html").write_text(
                await page.content(), encoding="utf-8"
            )
        except Exception as e:
            print(f"Ошибка сохранения артефактов: {e}")

        await context.close()
        await browser.close()

    return records, log_rows


async def main():
    try:
        records, log_rows = await collect_quotes_browser(max_iterations=30)
    except Exception as e:
        print(f"Фатальная ошибка сбора: {e}")
        sys.exit(1)

    if not records:
        print("Не собрано ни одной записи — завершение с ненулевым кодом.")
        sys.exit(1)

    with open("data_browser.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["text", "author", "tags"]
        )
        writer.writeheader()
        writer.writerows(records)

    with open("collection_log.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["iteration", "elements_on_page", "new_records",
                        "total", "duration_sec", "url", "timestamp"],
        )
        writer.writeheader()
        writer.writerows(log_rows)

    print(f"\nВсего собрано: {len(records)} записей.")
    print("Сохранено: data_browser.csv, collection_log.csv")


if __name__ == "__main__":
    start = time.time()
    asyncio.run(main())
    print('Прошло', round(time.time() - start, 4), 'секунд.')