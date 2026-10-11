#!/usr/bin/env python3
"""Inspect declarations filter inputs and perform a real search in the UI,
capturing the exact request/response."""
import json

from playwright.sync_api import sync_playwright

PROXY = "http://127.0.0.1:8899"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")

caps = []

with sync_playwright() as p:
    b = p.chromium.launch(headless=True, proxy={"server": PROXY},
                          args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
    ctx = b.new_context(user_agent=UA, locale="ru-RU", viewport={"width": 1700, "height": 1100})
    page = ctx.new_page()

    def on_resp(r):
        u = r.url
        if "/api/v1/" in u and ("declaration" in u or "/common/" in u):
            body = ""
            try:
                body = r.text()[:300]
            except Exception:
                pass
            caps.append({"url": u, "status": r.status, "body": body})
    page.on("response", on_resp)

    page.goto("https://pub.fsa.gov.ru/rss/certificate", wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(9000)
    page.get_by_text("Единый реестр сертификатов соответствия и деклараций").first.click()
    page.wait_for_timeout(1500)
    page.get_by_text("Декларации", exact=True).first.click()
    page.wait_for_timeout(7000)

    print("=== INPUT outerHTML ===")
    for e in page.query_selector_all("input"):
        try:
            print("  ", e.evaluate("e => e.outerHTML")[:220].replace('\\n', ' '))
        except Exception:
            pass

    print("\n=== labels / filter field wrappers ===")
    for e in page.query_selector_all("[class*=field], [class*=filter], label"):
        t = (e.inner_text() or "").strip()
        if t and len(t) < 60:
            print("   ", repr(t))

    # Try to fill the "Номер декларации" field: locate its label then the input
    print("\n=== attempting number search ===")
    try:
        lbl = page.get_by_text("Номер декларации о соответствии", exact=False).first
        box = lbl.bounding_box()
        print("   label box:", box)
        # the input is usually right after the label
        wrapper = lbl.evaluate_handle("e => e.closest('div')")
        inp = wrapper.as_element().query_selector("input")
        if inp:
            inp.fill("RU Д-RU")
            print("   filled input after label")
    except Exception as e:
        print("   err:", str(e)[:100])
    page.wait_for_timeout(1000)
    try:
        page.get_by_role("button", name="Найти").first.click(timeout=5000)
        print("   clicked Найти")
    except Exception as e:
        print("   Найти err", str(e)[:80])
    page.wait_for_timeout(8000)

    print("\n=== captured responses ===")
    for c in caps:
        print(f"  {c['status']} {c['url'].split('pub.fsa.gov.ru')[-1][:70]}  {c['body'][:120]}")
    b.close()
