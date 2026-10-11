#!/usr/bin/env python3
"""Probe the FSA declarations search endpoint with the exact body shape the site sends.

The browser posts to /api/v1/rds/common/declarations/get with:
  columnsSearch: [{"name": <col>, "search": <val>, "type": 0}]
(earlier we used "column" which produced 500 RDS-APP-9999).
"""
import json
import sys

import fsa_api


def decl_body(col, val, size=10, page=0, sort="declDate"):
    filt = {
        "status": [], "idDeclType": [], "idCertObjectType": [], "idProductType": [],
        "idGroupRU": [], "idGroupEEU": [], "idTechReg": [], "idApplicantType": [],
        "regDate": {"minDate": None, "maxDate": None},
        "endDate": {"minDate": None, "maxDate": None},
        "columnsSearch": [{"name": col, "search": val, "type": 0}],
        "number": None, "idProductOrigin": [], "idProductEEU": [], "idProductRU": [],
        "idDeclScheme": [], "awaitOperatorCheck": None, "editApp": None,
        "violationSendDate": None, "isProtocolInvalid": None, "checkerAIResult": None,
        "checkerAIProtocolsResults": None, "checkerAIProtocolsMistakes": None,
        "hiddenFromOpen": None,
    }
    return {"size": size, "page": page, "count": 0, "filter": filt,
            "columnsSort": [{"column": sort, "sort": "DESC"}]}


def try_search(col, val, size=10):
    tok = fsa_api.login()
    body = decl_body(col, val, size=size)
    st, data = fsa_api._req("POST", "/api/v1/rds/common/declarations/get",
                            body, token=tok)
    print(f"\n===== columnsSearch name={col!r} search={val!r}  ->  HTTP {st} =====")
    if not isinstance(data, (bytes, bytearray)):
        print(json.dumps(data, ensure_ascii=False)[:800])
        return st, data
    try:
        j = json.loads(data)
    except Exception:
        print("raw:", data[:400])
        return st, data
    if isinstance(j, dict):
        print("keys:", list(j.keys()))
        print(json.dumps(j, ensure_ascii=False)[:800])
    return st, j


if __name__ == "__main__":
    # sanity: empty columnsSearch (known to work)
    try_search("number", None, size=2)
    # real article search
    try_search("productIdentificationArticle", "фильтр", size=3)
    # declaration number search
    try_search("number", "RU Д", size=2)
    # product name
    try_search("productFullName", "фильтр", size=2)
