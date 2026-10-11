#!/usr/bin/env python3
"""Validate that declarations search actually filters by article (not ignored)."""
import json

import fsa_api
from test_decl_search import decl_body


def go(col, val, size=5):
    last = None
    for _ in range(4):
        try:
            tok = fsa_api.login()
            st, data = fsa_api._req("POST", "/api/v1/rds/common/declarations/get",
                                    decl_body(col, val, size=size), token=tok)
            j = json.loads(data)
            break
        except Exception as e:
            last = e
            print("   retry:", str(e)[:70])
    else:
        print("   FAILED:", last)
        return {}
    print(f"\n--- name={col!r} search={val!r} -> HTTP {st}, total={j.get('total')}, "
          f"returned={len(j.get('items') or [])}")
    return j


if __name__ == "__main__":
    j = go("productIdentificationArticle", "zzz_no_such_article_9x8y7z", size=3)
    go("productIdentificationArticle", "OC90", size=3)
    go("productIdentificationArticle", "фильтр", size=3)
    go("number", "ЕАЭС N RU Д-RU.РА09.А.45307", size=3)

    # full schema of one declaration item
    print("\n=== first item keys ===")
    it = (j.get("items") or [{}])[0]
    for k in sorted(it):
        v = it[k]
        print(f"  {k} = {str(v)[:90]}")
