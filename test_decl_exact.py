#!/usr/bin/env python3
"""Replicate the browser's exact declarations search body and check if it filters."""
import json
import os

os.environ.setdefault("SOCK_TIMEOUT", "45")
import fsa_api


def body(col, val, count=1000, size=10):
    return {"size": size, "page": 0, "count": count,
            "filter": {
                "status": [], "idDeclType": [], "idCertObjectType": [],
                "idProductType": [], "idGroupRU": [], "idGroupEEU": [],
                "idTechReg": [], "idApplicantType": [],
                "regDate": {"minDate": "", "maxDate": ""},
                "endDate": {"minDate": "", "maxDate": ""},
                "columnsSearch": [{"name": col, "search": val, "type": 0}],
            },
            "columnsSort": [{"column": "declDate", "sort": "DESC"}]}


def go(col, val, count=1000, size=10):
    for _ in range(5):
        try:
            tok = fsa_api.login()
            st, data = fsa_api._req("POST", "/api/v1/rds/common/declarations/get",
                                    body(col, val, count, size), token=tok)
            j = json.loads(data)
            break
        except Exception as e:
            print("   retry", str(e)[:50])
    else:
        print(f"\n{col}={val!r}: FAILED"); return
    items = j.get("items") or []
    print(f"\n### {col}={val!r} count={count} -> HTTP {st} total={j.get('total')} n={len(items)}")
    for it in items[:5]:
        print("     ", it.get("declNumber"), "|", str(it.get("productFullName"))[:45])


if __name__ == "__main__":
    go("number", "45307")
    go("number", "45307", count=0)
    go("productIdentificationArticle", "OC90")
    go("number", None)
    # what does an empty search return?
    print("\n(empty article search, sanity)")
    go("productFullName", "фильтр")
