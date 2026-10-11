#!/usr/bin/env python3
"""Test EAEU brand-wide search: speed + yield for TOYOTA / BMW productName."""
import json
import re
import time
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 Chrome/124.0",
      "Accept": "application/json"}
HOST = "https://tech.eaeunion.org"
BASE = HOST + "/odata/conformityDocDetailsType"


def get(url, timeout=120):
    t = time.time()
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace"), time.time() - t
    except Exception as e:
        return None, str(e), time.time() - t


def probe(label, filt, top=10, skip=0):
    url = (BASE + "?$filter=" + urllib.parse.quote(filt) +
           f"&$top={top}&$skip={skip}&$orderby=docId")
    st, body, dt = get(url)
    n = -1
    if st == 200:
        try:
            n = len(json.loads(body).get("value", []))
        except Exception:
            n = -2
    print(f"[{label}] {dt:.1f}s status={st} got={n}", flush=True)
    return st, body, dt


def main():
    # 1) TOYOTA in productName
    f1 = "technicalRegulationObjectDetails/productDetails/any(p: contains(p/productName,'TOYOTA'))"
    st, body, dt = probe("toyota productName", f1, top=10)
    # 2) TOYOTA in productTradeName (collection lambda)
    f2 = ("technicalRegulationObjectDetails/productDetails/any(p: "
          "p/productTradeName/any(t: contains(t,'TOYOTA')))")
    st, body, dt = probe("toyota tradeName", f2, top=10)
    # 3) BMW productName
    f3 = "technicalRegulationObjectDetails/productDetails/any(p: contains(p/productName,'BMW'))"
    st, body, dt = probe("bmw productName", f3, top=10)
    # 4) if any returned docs, dump a couple docIds + productNames
    for label, filt in [("toyota tradeName", f2), ("bmw productName", f3)]:
        st, body, dt = get(BASE + "?$filter=" + urllib.parse.quote(filt) +
                           "&$top=4&$orderby=docId")
        if st != 200:
            continue
        j = json.loads(body)
        docs = j.get("value", [])
        print(f"--- {label} sample ---")
        for d in docs[:4]:
            prods = ((d.get("technicalRegulationObjectDetails") or {})
                     .get("productDetails") or [])
            pn = (prods[0].get("productName") or "")[:140] if prods else ""
            print("   ", d.get("docId"), "|", d.get("conformityDocKindName"), "|", pn)
        if len(docs) == 10:
            # estimate total? server may omit count
            m = re.search(r'"@odata.count":(\d+)', body)
            print("   odata.count in answer:", m.group(1) if m else None)


if __name__ == "__main__":
    main()