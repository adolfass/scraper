#!/usr/bin/env python3
"""Find which columns the declarations endpoint allows in columnsSearch."""
import fsa_api


def t(desc, body):
    try:
        st, res = fsa_api._call("POST", "/api/v1/rds/common/declarations/get", body)
    except Exception as e:
        print(f"{desc}: ERR {str(e)[:50]}", flush=True)
        return
    if isinstance(res, dict):
        print(f"{desc}: {st} total={res.get('total')}", flush=True)
    else:
        print(f"{desc}: {st} {str(res)[:70]}", flush=True)


def base(col, q):
    return {"size": 3, "page": 0,
            "filter": {"columnsSearch": [{"column": col, "search": q}]},
            "columnsSort": [{"column": "id", "sort": "ASC"}]}


for col, q in [("number", "ТС N RU Д-RU"), ("manufacterName", "Cummins"),
               ("productFullName", "фильтр"),
               ("productIdentificationArticle", "фильтр"),
               ("productIdentificationName", "фильтр"),
               ("applicantName", "Cummins")]:
    t(f"col={col}", base(col, q))

t("idDeclScheme", {"size": 3, "page": 0,
                   "filter": {"idDeclScheme": [],
                              "columnsSearch": [{"column": "productIdentificationName",
                                                 "search": "фильтр"}]},
                   "columnsSort": [{"column": "id", "sort": "ASC"}]})
print("done", flush=True)
