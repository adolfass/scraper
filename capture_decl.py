#!/usr/bin/env python3
"""Open the FSA declarations registry in a real browser and capture what the
site actually sends/receives.

Chromium goes through en0_proxy.py (which binds upstream sockets to en0), so it
reaches pub.fsa.gov.ru despite the VPN. We record every request/response to
*.fsa.gov.ru together with headers (incl. the bearer token) and API bodies.

Usage:
    .venv/bin/python capture_decl.py [url]
"""
import json
import sys

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "https://pub.fsa.gov.ru/rds/declaration"
PROXY = "http://127.0.0.1:8899"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")

reqs = []
resps = []
console = []
errors = []


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, proxy={"server": PROXY}, args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
        ])
        ctx = browser.new_context(user_agent=UA, locale="ru-RU",
                                  viewport={"width": 1440, "height": 900})
        page = ctx.new_page()

        def on_request(r):
            if "fsa.gov.ru" in r.url:
                try:
                    hdrs = r.all_headers()
                except Exception:
                    hdrs = r.headers
                reqs.append({"method": r.method, "url": r.url,
                             "headers": hdrs, "post": r.post_data})

        def on_response(r):
            if "fsa.gov.ru" in r.url:
                body = None
                if "/api/" in r.url:
                    try:
                        body = r.text()[:4000]
                    except Exception as e:
                        body = f"<err {e}>"
                resps.append({"status": r.status, "url": r.url, "body": body})

        page.on("request", on_request)
        page.on("response", on_response)
        page.on("console", lambda m: console.append(f"{m.type}: {m.text}"[:300]))
        page.on("pageerror", lambda e: errors.append(str(e)[:300]))

        print(f"goto {URL}", flush=True)
        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=90000)
        except Exception as e:
            print("goto err:", e, flush=True)
        page.wait_for_timeout(12000)

        state = {}
        try:
            state["localStorage"] = page.evaluate("Object.fromEntries(Object.entries(localStorage))")
            state["sessionStorage"] = page.evaluate("Object.fromEntries(Object.entries(sessionStorage))")
            state["cookies"] = ctx.cookies()
            state["body_head"] = page.inner_text("body")[:1500]
        except Exception as e:
            state["err"] = str(e)

        browser.close()

    with open("/tmp/fsa_capture.json", "w", encoding="utf-8") as f:
        json.dump({"reqs": reqs, "resps": resps, "state": state}, f,
                  ensure_ascii=False, indent=1)

    print(f"\n=== {len(reqs)} requests, {len(resps)} responses ===")
    for r in reqs:
        auth = r["headers"].get("authorization") or r["headers"].get("Authorization") or ""
        if "/api/" in r["url"]:
            print(f"REQ  {r['method']:4} {r['url'][:110]}  auth={'Y' if auth else '-'}"
                  + (f"  post={str(r['post'])[:120]}" if r["post"] else ""))
    print("--- non-api page loads ---")
    for r in reqs[:20]:
        if "/api/" not in r["url"]:
            print(f"     {r['method']:4} {r['url'][:110]}")
    print("--- api responses ---")
    for r in resps:
        if "/api/" in r["url"]:
            print(f"RESP {r['status']} {r['url'][:110]}")
    print("\nstate keys:", {k: (len(v) if isinstance(v, (list, dict)) else str(v)[:80])
                            for k, v in state.items()})
    print("--- console ---")
    for c in console[-25:]:
        print("  ", c)
    print("--- page errors ---")
    for e in errors[-15:]:
        print("  ", e)


if __name__ == "__main__":
    main()
