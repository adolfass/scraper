#!/usr/bin/env python3
"""Does declarations/get actually filter? Print returned declNumber/product for a
targeted search vs a nonsense search."""
import json
import os

os.environ.setdefault("SOCK_TIMEOUT", "45")
import fsa_api
from test_decl_search import decl_body


def go(col, val, size=5, top=None):
    body = decl_body(col, val, size=size)
    if top:
        body["filter"].update(top)
    for _ in range(5):
        try:
            tok = fsa_api.login()
            st, data = fsa_api._req("POST", "/api/v1/rds/common/declarations/get",
                                    body, token=tok)
            j = json.loads(data)
            break
        except Exception as e:
            print("   retry:", str(e)[:60])
    else:
        print("   FAILED"); return {}
    print(f"\n--- {col}={val!r} top={top} -> HTTP {st} total={j.get('total')}")
    for it in (j.get("items") or [])[:5]:
        print("     ", it.get("declNumber"), "|", str(it.get("productFullName"))[:60])
    return j


if __name__ == "__main__":
    go("number", "45307")                 # substring of a real number
    go("number", "zzzznope12345")         # nonsense
    go("number", None, top={"number": "45307"})  # top-level number field
