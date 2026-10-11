#!/usr/bin/env python3
"""Probe: raw body of $filter responses from tech.eaeunion.org OData."""
import time
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 Chrome/124.0",
      "Accept": "application/json"}
HOST = "https://tech.eaeunion.org"


def get(url, timeout=60):
    t = time.time()
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(), time.time() - t
    except Exception as e:
        return None, str(e).encode(), time.time() - t


def q(filt):
    return HOST + "/odata/conformityDocDetailsType?$filter=" + urllib.parse.quote(filt) + "&$top=2"


def main():
    tests = [
        "contains(productName,'90915')",
        "contains(productName,'масляный фильтр')",
        "contains(productName,'90915yzzd2')",
        "contains(technicalRegulationId,'017/2011')",
    ]
    for filt in tests:
        st, body, dt = get(q(filt))
        print(f"filter={filt!r}\n  status={st} {dt:.1f}s len={len(body)}")
        if st is not None:
            print("  body:", body[:500].decode("utf-8", "replace").replace("\n", " "))
        print()

    st, body, dt = get(HOST + "/odata/conformityDocDetailsType?$count=true&$top=0")
    print(f"count=true: status={st} {dt:.1f}s len={len(body)} body={body[:300]!r}")


if __name__ == "__main__":
    main()