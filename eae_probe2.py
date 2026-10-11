#!/usr/bin/env python3
"""Validate EAEU OData lambda filter on productDetailscollection."""
import json
import time
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 Chrome/124.0",
      "Accept": "application/json"}
HOST = "https://tech.eaeunion.org"
BASE = HOST + "/odata/conformityDocDetailsType"


def get(url, timeout=90):
    t = time.time()
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace"), time.time() - t
    except Exception as e:
        return None, str(e), time.time() - t


def probe(label, filt, top=3):
    url = BASE + "?$filter=" + urllib.parse.quote(filt) + f"&$top={top}"
    st, body, dt = get(url)
    print(f"[{label}] filter={filt!r}\n  status={st} {dt:.1f}s len={len(body)}")
    if st == 200:
        try:
            j = json.loads(body)
            vals = j.get("value", [])
            print(f"  results: {len(vals)}")
        except Exception as e:
            print(f"  parse error {e}: {body[:200]}")
    else:
        print(f"  {body[:200]}")
    print()
    return st, body


def main():
    # 1) positive control: dump one doc fully (productName/productText/commodityCode/manufacturer)
    url = BASE + "?$top=1"
    st, body, dt = get(url)
    j = json.loads(body)["value"][0]
    tro = j.get("technicalRegulationObjectDetails") or {}
    prods = tro.get("productDetails") or []
    print(f"control doc {j.get('docId')}: {len(prods)} products")
    for p in prods[:2]:
        print("   productName:", (p.get("productName") or "")[:220])
        print("   productText:", (p.get("productText") or "")[:220])
        print("   commodityCode:", p.get("commodityCode"))
    mfrs = tro.get("manufacturerDetails") or []
    for m in mfrs[:2]:
        print("   manufacturer:", (m.get("businessEntityName") or "")[:120])
    print()

    # 2) validate lambda filter with a token from the control doc
    token = (prods[0].get("productName") or "").strip()
    tokens = [t for t in token.replace(",", " ").split() if len(t) >= 6]
    if tokens:
        probe("any(productName) control",
              f"technicalRegulationObjectDetails/productDetails/any(p: contains(p/productName,'{tokens[0]}'))")
    else:
        print("no token in control doc productName; skip positive control")
    probe("any(productName) toyota", 
          "technicalRegulationObjectDetails/productDetails/any(p: contains(p/productName,'90915yzzd2'))")
    probe("any(productText) toyota",
          "technicalRegulationObjectDetails/productDetails/any(p: contains(p/productText,'90915yzzd2'))")
    probe("any(productText) bmw",
          "technicalRegulationObjectDetails/productDetails/any(p: contains(p/productText,'17222248641'))")
    probe("any(productName) vag",
          "technicalRegulationObjectDetails/productDetails/any(p: contains(p/productName,'06c121397b'))")


if __name__ == "__main__":
    main()