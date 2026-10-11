#!/usr/bin/env python3
"""Map each declarations filter text input to its field label."""
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

    out = page.evaluate("""() => {
        const res = [];
        document.querySelectorAll('input[data-pc-name="pcfilterinputtext"]').forEach((inp,i) => {
            // climb until an ancestor contains a short label text
            let node = inp, label='';
            for (let k=0;k<6 && node;k++){
                const txt=(node.innerText||'').trim().split('\\n')[0];
                if (txt && txt.length<60 && !/^\\d+$/.test(txt)){ label=txt; break; }
                node=node.parentElement;
            }
            res.push([i, label, inp.getAttribute('formcontrolname')||inp.getAttribute('name')||'']);
        });
        // also find the filter submit button
        const btns=[...document.querySelectorAll('button')].map(b=>b.innerText.trim()).filter(Boolean);
        return {inputs:res, buttons:btns};
    }""")
    for row in out["inputs"]:
        print("input", row)
    print("buttons:", out["buttons"])
    b.close()
