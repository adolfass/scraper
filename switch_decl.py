#!/usr/bin/env python3
"""Find the certificates<->declarations switcher and drive it, capturing the
declarations API request."""
import json

from playwright.sync_api import sync_playwright

PROXY = "http://127.0.0.1:8899"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")

reqs, resps = [], []

with sync_playwright() as p:
    b = p.chromium.launch(headless=True, proxy={"server": PROXY},
                          args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
    ctx = b.new_context(user_agent=UA, locale="ru-RU", viewport={"width": 1440, "height": 1000})
    page = ctx.new_page()
    page.on("request", lambda r: reqs.append(r) if "/api/" in r.url else None)
    page.on("response", lambda r: resps.append(r) if "/api/" in r.url else None)

    page.goto("https://pub.fsa.gov.ru/rss/certificate", wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(10000)

    # dump header HTML around the registry title
    try:
        el = page.query_selector("text=Единый реестр сертификатов")
        h = el.evaluate("e => e.closest('header,div,section') ? e.closest('header,div,section').outerHTML : e.outerHTML")
        print("=== header HTML (first 2000) ===")
        print(h[:2000])
    except Exception as e:
        print("hdr err", e)

    # list candidate clickables containing 'ертификат' or 'екларац'
    print("\n=== clickable candidates ===")
    for sel in ["a", "button", "[role=button]", "[class*=select]", "[class*=dropdown]", "[class*=menu]"]:
        try:
            for e in page.query_selector_all(sel):
                t = (e.inner_text() or "").strip()
                if t and ("ертификат" in t or "екларац" in t) and len(t) < 80:
                    print(f"  {sel}: {t!r}")
        except Exception:
            pass

    # try to open the switcher: click the element with the full registry title
    print("\n=== trying to click switcher ===")
    clicked = False
    for attempt in [
        lambda: page.get_by_text("Единый реестр сертификатов соответствия и деклараций").first.click(timeout=5000),
        lambda: page.locator("[class*=select], [class*=dropdown], [class*=menu]").first.click(timeout=5000),
    ]:
        try:
            attempt()
            clicked = True
            break
        except Exception as e:
            print("   click fail:", str(e)[:80])
    page.wait_for_timeout(2500)

    print("\n=== after click, body text (first 1200) ===")
    print(page.inner_text("body")[:1200])

    # now try to click 'Декларации'
    print("\n=== trying to select Декларации ===")
    for lbl in ["Декларации", "Декларация", "Реестр деклараций"]:
        try:
            page.get_by_text(lbl, exact=False).first.click(timeout=4000)
            print("   clicked:", lbl)
            break
        except Exception as e:
            print(f"   {lbl}: {str(e)[:60]}")
    page.wait_for_timeout(8000)

    print("\n=== body text after switch (first 1200) ===")
    print(page.inner_text("body")[:1200])

    print("\n=== api requests ===")
    for r in reqs:
        print(f"  {r.method:4} {r.url.split('pub.fsa.gov.ru')[-1][:80]} post={str(r.post_data)[:150]}")
    print("\n=== api responses ===")
    for r in resps:
        body = ""
        try:
            body = r.text()[:120]
        except Exception:
            pass
        print(f"  {r.status} {r.url.split('pub.fsa.gov.ru')[-1][:80]} {body}")
    b.close()
