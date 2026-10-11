#!/usr/bin/env python3
"""Confirm declarations article search + inspect item schema + detail endpoint."""
import json
import os

os.environ.setdefault("SOCK_TIMEOUT", "60")
import fsa_api
from test_decl_exact import body


def call(col, val, size=10, tries=8):
    for i in range(tries):
        try:
            tok = fsa_api.login()
            st, data = fsa_api._req("POST", "/api/v1/rds/common/declarations/get",
                                    body(col, val, size=size), token=tok)
            return st, json.loads(data)
        except Exception as e:
            print("   retry", i, str(e)[:45])
    return None, None


if __name__ == "__main__":
    for art in ["OC90", "W712", "OC217", "фильтр"]:
        st, j = call("productIdentificationArticle", art)
        if j is None:
            print(f"\n{art}: FAILED"); continue
        items = j.get("items") or []
        print(f"\n### article={art!r} HTTP {st} total={j.get('total')} n={len(items)}")
        for it in items[:4]:
            print("     ", it.get("declNumber"), "|", str(it.get("productFullName"))[:55])
        if art == "OC90" and items:
            print("\n=== item keys ===")
            for k in sorted(items[0]):
                print(f"  {k} = {str(items[0][k])[:80]}")
