#!/usr/bin/env python3
"""Pilot: can tech.eaeunion.org OData find our articles in productName free-text?

Reachability + $filter=contains(...) probe, then for a handful of weak-brand
articles check whether any conformity doc mentions them.
"""
import json
import time
import urllib.parse
import urllib.request

from curl_cffi import requests as creq

HOST = "https://tech.eaeunion.org"
UA = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0",
    "Accept": "application/json",
}
SAMPLES = [
    ("toyota", "90915yzzd2"),
    ("toyota", "3356312050"),
    ("bmw", "17222248641"),
    ("bmw", "11538475192"),
    ("vag", "06c121397b"),
    ("li auto", "x0128030086"),
    ("geely", "1046033100"),
    ("land rover", "lr072510"),
    ("ford", "5017903"),
]


def urllib_get(url, timeout=40):
    t = time.time()
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(), time.time() - t
    except Exception as e:
        return None, str(e).encode(), time.time() - t


def main():
    # 1) structure of one item
    st, body, dt = urllib_get(HOST + "/odata/conformityDocDetailsType?$top=1")
    print(f"top=1: status={st} {dt:.1f}s len={len(body)}", flush=True)
    if st == 200:
        j = json.loads(body)
        it = j["value"][0]
        print("keys:", list(it.keys()))
        for k, v in it.items():
            vs = str(v)
            if len(vs) > 160:
                vs = vs[:160] + "…"
            print(f"  {k}: {vs!r}")
    print("---", flush=True)

    # 2) contains filter on productName
    for brand, code in SAMPLES:
        filt = f"contains(productName,'{code}')"
        url = (HOST + "/odata/conformityDocDetailsType?$filter="
               + urllib.parse.quote(filt) + "&$top=5")
        st, body, dt = urllib_get(url)
        if st != 200:
            print(f"{brand!r} {code!r}: status={st} {dt:.1f}s "
                  f"[{body[:90]!r}]", flush=True)
            continue
        try:
            n = len(json.loads(body).get("value", []))
        except Exception:
            n = -1
        print(f"{brand!r} {code!r}: status=200 n={n} {dt:.1f}s", flush=True)
        if n > 0:
            j = json.loads(body)
            for doc in j["value"][:2]:
                print("      docId=", doc.get("docId"),
                      "status=", doc.get("status"),
                      "regDate=", doc.get("registrationDate"))
                pn = str(doc.get("productName", ""))[:180]
                print("      [", pn, "]")


if __name__ == "__main__":
    main()