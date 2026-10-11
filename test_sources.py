#!/usr/bin/env python3
"""Probe other certificate sources: FSA declarations + EAEU registry."""
import json, urllib.request
import fsa_api

codes = ["s202f2604010500", "224412m810", "301416546", "timken94771554"]

# 1) try FSA declaration endpoints
endpoints = [
    "/api/v1/rss/common/declarations/get",
    "/api/v1/rss/common/declaration/get",
    "/api/v1/rss/declarations/get",
    "/api/v1/rss/common/declarations/search",
]
for ep in endpoints:
    body = {"size": 5, "page": 0,
            "filter": {"columnsSearch": [
                {"column": "productIdentificationArticle",
                 "search": codes[0]}]},
            "columnsSort": [{"column": "id", "sort": "ASC"}]}
    try:
        st, res = fsa_api._call("POST", ep, body)
        desc = ""
        if isinstance(res, dict):
            desc = f"total={res.get('total')} keys={list(res)[:5]}"
        print(f"{ep}: http {st} {desc}", flush=True)
    except Exception as e:
        print(f"{ep}: ERR {str(e)[:60]}", flush=True)

# 2) check searchable columns on certificates: is declarations in same data?
print("---", flush=True)
st, res = fsa_api.search_certificates(
    columns_search=[{"column": "productIdentificationArticle", "search": codes[1]}],
    size=5)
print("certs for", codes[1], "->", st, res.get("total") if isinstance(res, dict) else res, flush=True)
