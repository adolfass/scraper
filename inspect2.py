#!/usr/bin/env python3
"""Locate the declarations 'Номер' filter input via its label and dump HTML."""
from playwright.sync_api import sync_playwright

PROXY = "http://127.0.0.1:8899"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")

with sync_playwright() as p:
    b = p.chromium.launch(headless=True, proxy={"server": PROXY},
                          args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
    ctx = b.new_context(user_agent=UA, locale="ru-RU", viewport={"width": 1700, "height": 1100})
    page = ctx.new_page()
    page.goto("https://pub.fsa.gov.ru/rss/certificate", wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(9000)
    page.get_by_text("Единый реестр сертификатов соответствия и деклараций").first.click()
    page.wait_for_timeout(1500)
    page.get_by_text("Декларации", exact=True).first.click()
    page.wait_for_timeout(7000)

    html = page.evaluate("""() => {
        const all = [...document.querySelectorAll('*')];
        const lbl = all.find(e => e.children.length===0 &&
            e.textContent.trim()==='Номер декларации о соответствии');
        if (!lbl) return 'label not found';
        let node = lbl;
        for (let i=0;i<6 && node;i++){
            if (node.querySelector && node.querySelector('input'))
                return node.outerHTML.slice(0,600);
            node = node.parentElement;
        }
        return 'no input near label; parent=' + (lbl.parentElement? lbl.parentElement.outerHTML.slice(0,400):'');
    }""")
    print("HTML near label:\n", html)

    # Try get_by_label
    try:
        loc = page.get_by_label("Номер декларации о соответствии")
        print("get_by_label count:", loc.count())
    except Exception as e:
        print("get_by_label err", str(e)[:80])
    b.close()
