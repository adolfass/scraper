#!/usr/bin/env python3
"""Dump the FSA registry UI: title, visible text, links, buttons, switches."""
import sys

from playwright.sync_api import sync_playwright

PROXY = "http://127.0.0.1:8899"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")

with sync_playwright() as p:
    b = p.chromium.launch(headless=True, proxy={"server": PROXY},
                          args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
    ctx = b.new_context(user_agent=UA, locale="ru-RU", viewport={"width": 1440, "height": 1000})
    page = ctx.new_page()
    page.goto("https://pub.fsa.gov.ru/rss/certificate", wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(12000)

    print("TITLE:", page.title())
    print("\n=== HREFS ===")
    for a in page.eval_on_selector_all("a", "els => els.map(e => [e.innerText.trim(), e.getAttribute('href')])"):
        if a[0] or a[1]:
            print("  ", a)
    print("\n=== BUTTONS ===")
    for x in page.eval_on_selector_all("button", "els => els.map(e => e.innerText.trim()).filter(Boolean)"):
        print("  ", x[:60])
    print("\n=== body text (first 3000) ===")
    print(page.inner_text("body")[:3000])
    b.close()
