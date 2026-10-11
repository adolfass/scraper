#!/usr/bin/env python3
"""Switch to declarations, list the filter inputs, fill the article field, hit
'Найти', and capture the exact POST body the site sends."""
import json

from playwright.sync_api import sync_playwright

PROXY = "http://127.0.0.1:8899"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")

captured = []

with sync_playwright() as p:
    b = p.chromium.launch(headless=True, proxy={"server": PROXY},
                          args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
    ctx = b.new_context(user_agent=UA, locale="ru-RU", viewport={"width": 1600, "height": 1100})
    page = ctx.new_page()

    def on_req(r):
        if "/api/v1/rds/" in r.url and r.method == "POST":
            captured.append((r.url, r.post_data))
    page.on("request", on_req)

    page.goto("https://pub.fsa.gov.ru/rss/certificate", wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(9000)

    # switch to declarations
    page.get_by_text("Единый реестр сертификатов соответствия и деклараций").first.click()
    page.wait_for_timeout(1500)
    page.get_by_text("Декларации", exact=True).first.click()
    page.wait_for_timeout(7000)

    print("=== INPUTS (placeholder / type / name) ===")
    for e in page.query_selector_all("input"):
        try:
            print("  ", repr(e.get_attribute("placeholder")), e.get_attribute("type"),
                  e.get_attribute("formcontrolname") or e.get_attribute("name"))
        except Exception:
            pass

    # try to fill the article field by placeholder
    targets = ["Артикул", "артикул", "Номер декларации", "Общее наименование"]
    filled = False
    for ph in targets:
        try:
            loc = page.get_by_placeholder(ph, exact=False).first
            if loc.count() if hasattr(loc, "count") else True:
                loc.fill("фильтр", timeout=4000)
                print("filled placeholder:", ph)
                filled = True
                break
        except Exception as e:
            print(f"  fill {ph}: {str(e)[:50]}")
    if not filled:
        # fallback: fill the first visible text input
        try:
            page.locator("input:visible").first.fill("фильтр")
            print("filled first visible input")
        except Exception as e:
            print("fallback fill err", e)

    page.wait_for_timeout(1000)
    # click Найти
    try:
        page.get_by_role("button", name="Найти").first.click(timeout=5000)
        print("clicked Найти")
    except Exception as e:
        print("Найти err", str(e)[:80])
    page.wait_for_timeout(9000)

    print("\n=== rds POST requests ===")
    for u, body in captured:
        print("URL:", u)
        print("BODY:", str(body)[:1200])

    print("\n=== body text (first 900) ===")
    print(page.inner_text("body")[:900])
    b.close()
