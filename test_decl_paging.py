#!/usr/bin/env python3
"""Check declarations paging stability (sort by id) and the detail endpoint."""
import json
import os

os.environ.setdefault("SOCK_TIMEOUT", "60")
import fsa_api
from test_decl_exact import body


def call(body_, path="/api/v1/rds/common/declarations/get", method="POST", tries=8):
    for i in range(tries):
        try:
            tok = fsa_api.login()
            st, data = fsa_api._req(method, path, body_ if method == "POST" else None,
                                    token=tok)
            try:
                return st, json.loads(data)
            except Exception:
                return st, data
        except Exception as e:
            print("   retry", i, str(e)[:45])
    return None, None


def page(col, val, p, size=5, sort="id", order="ASC"):
    b = body(col, val, size=size)
    b["page"] = p
    b["columnsSort"] = [{"column": sort, "sort": order}]
    st, j = call(b)
    items = (j or {}).get("items") or []
    ids = [it.get("id") for it in items]
    print(f"  page {p} sort={sort} {order}: HTTP {st} n={len(ids)} ids={ids}")
    return ids


if __name__ == "__main__":
    print("== paging by id ASC (article 'фильтр') ==")
    a = page("productIdentificationArticle", "фильтр", 0)
    b = page("productIdentificationArticle", "фильтр", 1)
    c = page("productIdentificationArticle", "фильтр", 2)
    print("  overlap 0&1:", set(a) & set(b), " 0&2:", set(a) & set(c))

    print("\n== paging by declDate DESC (default) ==")
    page("productIdentificationArticle", "фильтр", 0, sort="declDate", order="DESC")
    page("productIdentificationArticle", "фильтр", 1, sort="declDate", order="DESC")

    print("\n== detail endpoint /api/v1/rds/common/declarations/19116625 ==")
    st, j = call(None, path="/api/v1/rds/common/declarations/19116625", method="GET")
    print("  HTTP", st, "keys:", list(j.keys()) if isinstance(j, dict) else str(j)[:200])
    if isinstance(j, dict):
        d = j.get("data", j)
        print("  sample:", json.dumps(d, ensure_ascii=False)[:500])
