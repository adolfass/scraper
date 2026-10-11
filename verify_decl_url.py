#!/usr/bin/env python3
"""Verify that the declaration view URL renders a card for a known id."""
import sys

from playwright.sync_api import sync_playwright

PROXY = "http://127.0.0.1:8899"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")

did = sys.argv[1] if len(sys.argv) > 1 else "19116625"
urls = [f"https://pub.fsa.gov.ru/rds/declaration/view/{did}",
        f"https://pub.fsa.gov.ru/rds/declaration/view/{did}/product"]

with sync_playwright() as p:
    b = p.chromium.launch(headless=True, proxy={"server": PROXY},
                          args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
    ctx = b.new_context(user_agent=UA, locale="ru-RU", viewport={"width": 1400, "height": 900})
    page = ctx.new_page()
    for u in urls:
        try:
            page.goto(u, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(9000)
            txt = page.inner_text("body")
            ok = "Д-CN.РА06.В.13746" in txt or "13746" in txt
            print(f"{u}\n   RENDERS={ok}  len={len(txt)}\n   head: {txt[:180]!r}")
        except Exception as e:
            print(f"{u}\n   ERR {str(e)[:100]}")
    b.close()
