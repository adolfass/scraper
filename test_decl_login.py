#!/usr/bin/env python3
"""Check whether a personal FSA account unlocks the declarations registry (rds).

Usage:
    FSA_USER=... FSA_PASS=... .venv/bin/python test_decl_login.py

Prints:
  * who we logged in as (sub claim) and token length;
  * whether the declarations list (empty) is readable;
  * whether search by article works (this is the whole point);
  * whether applications/get still returns 403.
"""
import json
import os
import base64

import fsa_api

USER = os.environ.get("FSA_USER", "anonymous")


def sub_of(tok):
    try:
        p = tok.split(".")[1]
        p += "=" * (-len(p) % 4)
        return json.loads(base64.urlsafe_b64decode(p)).get("sub")
    except Exception:
        return "?"


def decl_filter(cs):
    return {"status": [], "idDeclType": [], "idCertObjectType": [],
            "idProductType": [], "idGroupRU": [], "idGroupEEU": [],
            "idTechReg": [], "idApplicantType": [],
            "regDate": {"minDate": "", "maxDate": ""},
            "endDate": {"minDate": "", "maxDate": ""},
            "columnsSearch": cs}


def probe(path, cs, label):
    body = {"size": 5, "page": 0, "count": 0,
            "filter": decl_filter(cs), "columnsSort": []}
    try:
        st, res = fsa_api._call("POST", path, body)
    except Exception as e:
        print(f"  {label}: ERR {str(e)[:60]}", flush=True)
        return
    if isinstance(res, dict):
        print(f"  {label}: http {st} total={res.get('total')}", flush=True)
        items = res.get("items") or []
        if st == 200 and items:
            it = items[0]
            print("      sample:", {k: it.get(k) for k in (
                "declNumber", "manufacterName",
                "productIdentificationArticle", "productIdentificationName")},
                flush=True)
    else:
        print(f"  {label}: http {st} {str(res)[:80]}", flush=True)


def main():
    tok = fsa_api.login(force=True)
    print(f"login as {USER!r}  sub={sub_of(tok)}  token_len={len(tok)}", flush=True)

    print("declarations/get:", flush=True)
    probe("/api/v1/rds/common/declarations/get", [], "empty")
    probe("/api/v1/rds/common/declarations/get",
          [{"column": "productIdentificationArticle", "search": "фильтр"}], "article=фильтр")
    probe("/api/v1/rds/common/declarations/get",
          [{"column": "manufacterName", "search": "фильтр"}], "manuf=фильтр")

    print("applications/get (declaration cabinet):", flush=True)
    probe("/api/v1/rds/common/applications/get", [], "empty")

    print("certificates (sanity):", flush=True)
    st, res = fsa_api.search_certificates(
        columns_search=[{"column": "productIdentificationArticle", "search": "фильтр"}], size=3)
    print(f"  certs: http {st} total={res.get('total') if isinstance(res, dict) else res}",
          flush=True)


if __name__ == "__main__":
    main()
