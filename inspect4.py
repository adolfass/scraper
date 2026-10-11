#!/usr/bin/env python3
"""Dump the declarations filter panel HTML (labels + bindings)."""
import sys
import time

from playwright.sync_api import sync_playwright

PROXY = "http://127.0.0.1:8899"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")


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
    err = None
    for attempt in range(3):
        try:
            switch(page)
            err = None
            break
        except Exception as e:
            err = e
            print("attempt", attempt, "failed:", str(e)[:80])
            time.sleep(3)
    if err:
        print("could not switch"); b.close(); sys.exit(1)

    html = page.evaluate("""() => {
        const inputs=[...document.querySelectorAll('input[data-pc-name="pcfilterinputtext"]')];
        if(!inputs.length) return 'no inputs';
        // smallest common ancestor
        let a=inputs[0];
        while(a && !inputs.every(i=>a.contains(i))) a=a.parentElement;
        return a ? a.outerHTML : 'no ancestor';
    }""")
    print(html[:4000])
    b.close()
