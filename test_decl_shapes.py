#!/usr/bin/env python3
"""Find which columnsSearch shape actually filters the declarations endpoint."""
import json
import os

os.environ.setdefault("SOCK_TIMEOUT", "45")
import fsa_api


def base_filter(cs):
    return {
        "status": [], "idDeclType": [], "idCertObjectType": [], "idProductType": [],
        "idGroupRU": [], "idGroupEEU": [], "idTechReg": [], "idApplicantType": [],
        "regDate": {"minDate": None, "maxDate": None},
        "endDate": {"minDate": None, "maxDate": None},
        "columnsSearch": cs,
    }


def run(label, cs, size=5):
    body = {"size": size, "page": 0, "count": 0, "filter": base_filter(cs),
            "columnsSort": [{"column": "declDate", "sort": "DESC"}]}
    for _ in range(5):
        try:
            tok = fsa_api.login()
            st, data = fsa_api._req("POST", "/api/v1/rds/common/declarations/get",
                                    body, token=tok)
            j = json.loads(data)
            break
        except Exception as e:
            print("   retry", str(e)[:50])
    else:
        print(f"\n### {label}: FAILED"); return
    items = j.get("items") or []
    print(f"\n### {label}\n    HTTP {st} total={j.get('total')} returned={len(items)}")
    for it in items[:3]:
        print("      ", it.get("declNumber"), "|", str(it.get("productFullName"))[:50])


if __name__ == "__main__":
    run("A column=article OC90",
        [{"column": "productIdentificationArticle", "search": "OC90"}])
    run("B name=article OC90 type0",
        [{"name": "productIdentificationArticle", "search": "OC90", "type": 0}])
    run("C column=number 45307",
        [{"column": "number", "search": "45307"}])
    run("D name=number 45307 type9",
        [{"name": "number", "search": "45307", "type": 9}])
    run("E column=productFullName фильтр",
        [{"column": "productFullName", "search": "фильтр"}])
