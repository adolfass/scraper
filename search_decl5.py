#!/usr/bin/env python3
"""Type into a column inline filter, press Enter, capture request body + response."""
import json
import time

from playwright.sync_api import sync_playwright

PROXY = "http://127.0.0.1:8899"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")

reqs, resps = [], []


def switch(page):
    page.goto("https://pub.fsa.gov.ru/rss/certificate", wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(10000)
    page.get_by_text("Единый реестр сертификатов соответствия и деклараций").first.click(timeout=20000)
    page.wait_for_timeout(2000)
    page.get_by_text("Декларации", exact=True).first.click(timeout=20000)
    page.wait_for_timeout(9000)


with sync_playwright() as p:
    b = p.chromium.launch(headless=True, proxy={"server": PROXY},
                          args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
    ctx = b.new_context(user_agent=UA, locale="ru-RU", viewport={"width": 1700, "height": 1100})
    page = ctx.new_page()

    def on_req(r):
        if "/api/v1/rds/common/declarations/get" in r.url:
            reqs.append(r.post_data)
    def on_resp(r):
        if "/api/v1/rds/common/declarations/get" in r.url:
            try:
                resps.append((r.status, r.text()[:200]))
            except Exception:
                resps.append((r.status, "<no body>"))
    page.on("request", on_req)
    page.on("response", on_resp)

    for attempt in range(3):
        try:
            switch(page); break
        except Exception as e:
            print("switch attempt", attempt, str(e)[:70]); time.sleep(3)

    f = page.locator('input[data-pc-name="pcfilterinputtext"]')
    print("column filter inputs:", f.count())
    first = f.first
    first.click()
    page.keyboard.type("45307", delay=70)
    page.keyboard.press("Enter")
    print("typed + Enter; value =", first.input_value())
    page.wait_for_timeout(9000)

    print("\n=== request bodies ===")
    for i, body in enumerate(reqs):
        print(f"#{i}: {str(body)[:520]}")
    print("\n=== responses (status, first 200) ===")
    for i, (st, body) in enumerate(resps):
        print(f"#{i}: {st}  {body}")
    b.close()
