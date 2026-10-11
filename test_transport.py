#!/usr/bin/env python3
"""Compare request reliability/latency: urllib (new TLS each time) vs curl_cffi
(persistent session, browser impersonation) on the declarations endpoint."""
import json
import os
import time

os.environ.setdefault("SOCK_TIMEOUT", "45")
import fsa_api
from test_decl_exact import body

TOK = fsa_api.login()
URL = "https://pub.fsa.gov.ru/api/v1/rds/common/declarations/get"
HDRS = {"User-Agent": fsa_api.UA, "Accept": "application/json",
        "Content-Type": "application/json", "origin": fsa_api.BASE,
        "authorization": "Bearer " + TOK}
B = body("productIdentificationArticle", "фильтр", size=5)

N = 10


def bench_urllib():
    print("== urllib ==")
    ok = 0
    for i in range(N):
        t = time.time()
        try:
            st, data = fsa_api._req_impl("POST", URL, B, TOK, timeout=45)
            ok += st == 200
            print(f"  {i}: {st} {time.time()-t:.1f}s")
        except Exception as e:
            print(f"  {i}: ERR {str(e)[:40]} {time.time()-t:.1f}s")
    print("  ok", ok, "/", N)


def bench_curl(proxy=True, interface=None):
    from curl_cffi import requests as creq
    kw = {"impersonate": "chrome", "timeout": 60}
    if proxy:
        kw["proxy"] = "http://127.0.0.1:8899"
    if interface:
        kw["interface"] = interface
    s = creq.Session(**kw)
    print(f"== curl_cffi proxy={proxy} interface={interface} ==")
    ok = 0
    for i in range(N):
        t = time.time()
        try:
            r = s.post(URL, data=json.dumps(B).encode(), headers=HDRS)
            ok += r.status_code == 200
            print(f"  {i}: {r.status_code} {time.time()-t:.1f}s len={len(r.content)}")
        except Exception as e:
            print(f"  {i}: ERR {str(e)[:45]} {time.time()-t:.1f}s")
    print("  ok", ok, "/", N)


if __name__ == "__main__":
    import sys
    which = sys.argv[1] if len(sys.argv) > 1 else "curl"
    if which == "urllib":
        bench_urllib()
    elif which == "interface":
        bench_curl(proxy=False, interface="en0")
    else:
        bench_curl()
