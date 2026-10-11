#!/usr/bin/env python3
"""Type into the declarations 'Номер' filter with real keystrokes and capture the
resulting request body."""
from playwright.sync_api import sync_playwright

PROXY = "http://127.0.0.1:8899"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")

reqs = []

with sync_playwright() as p:
    b = p.chromium.launch(headless=True, proxy={"server": PROXY},
                          args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
    ctx = b.new_context(user_agent=UA, locale="ru-RU", viewport={"width": 1700, "height": 1100})
    page = ctx.new_page()
    page.on("request", lambda r: reqs.append(r.post_data)
            if "/api/v1/rds/common/declarations/get" in r.url else None)

    page.goto("https://pub.fsa.gov.ru/rss/certificate", wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(9000)
    page.get_by_text("Единый реестр сертификатов соответствия и деклараций").first.click()
    page.wait_for_timeout(1500)
    page.get_by_text("Декларации", exact=True).first.click()
    page.wait_for_timeout(7000)

    f = page.locator('input[data-pc-name="pcfilterinputtext"]')
    print("filter input count:", f.count())
    first = f.first
    first.click()
    page.keyboard.type("45307", delay=60)
    page.wait_for_timeout(500)
    print("value after typing:", first.input_value())

    try:
        page.get_by_role("button", name="Найти").first.click(timeout=5000)
        print("clicked Найти")
    except Exception as e:
        print("Найти err", str(e)[:80])
    page.wait_for_timeout(8000)

    print("\n=== bodies ===")
    for i, body in enumerate(reqs):
        print(f"#{i}: {str(body)[:650]}")
    b.close()
