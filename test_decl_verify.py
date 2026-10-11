#!/usr/bin/env python3
"""Verify declarations article search semantics: nonsense vs real, paging, counts."""
import json
import os

os.environ.setdefault("SOCK_TIMEOUT", "60")
import fsa_api
from test_decl_exact import body


def call(col, val, size=100, page=0, tries=8):
    b = body(col, val, size=size)
    b["page"] = page
    for i in range(tries):
        try:
            tok = fsa_api.login()
            st, data = fsa_api._req("POST", "/api/v1/rds/common/declarations/get",
                                    b, token=tok)
            return st, json.loads(data)
        except Exception as e:
            print("   retry", i, str(e)[:40])
    return None, None


def report(label, col, val, size=100, page=0):
    st, j = call(col, val, size=size, page=page)
    if j is None:
        print(f"{label}: FAILED"); return
    items = j.get("items") or []
    arts = [it.get("productIdentificationArticle") or "" for it in items]
    hits = sum(1 for a in arts if val.lower() in a.lower()) if val else 0
    print(f"{label}: HTTP {st} total={j.get('total')} n={len(items)} "
          f"containing {val!r}: {hits}")
    return items


if __name__ == "__main__":
    report("nonsense   ", "productIdentificationArticle", "qzq_nope_123")
    report("OC90 p0    ", "productIdentificationArticle", "OC90")
    report("OC90 p1    ", "productIdentificationArticle", "OC90", page=1)
    report("фильтр     ", "productIdentificationArticle", "фильтр")
    report("empty      ", "productIdentificationArticle", "")
