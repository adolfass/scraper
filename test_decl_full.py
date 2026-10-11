import fsa_api

def decl_filter(search):
    return {"status": [], "columnsSearch": search, "idDeclType": [],
            "idCertObjectType": [], "idProductType": [], "idProductOrigin": [],
            "idGroup": [], "idApplicantType": [],
            "appDate": {"minDate": "", "maxDate": ""}}

def t(desc, filt):
    body = {"size": 3, "page": 0, "filter": filt,
            "columnsSort": [{"column": "id", "sort": "ASC"}]}
    try:
        st, res = fsa_api._call("POST", "/api/v1/rds/common/declarations/get", body)
    except Exception as e:
        print(f"{desc}: ERR {str(e)[:50]}", flush=True); return
    if isinstance(res, dict):
        n = res.get("total")
        print(f"{desc}: {st} total={n}", flush=True)
        items = res.get("items") or []
        if st == 200 and items:
            print("   sample:", {k: items[0].get(k) for k in
                  ("declNumber", "declDate", "manufacterName",
                   "productIdentificationArticle", "productIdentificationName")},
                  flush=True)
    else:
        print(f"{desc}: {st} {str(res)[:60]}", flush=True)

# no search, full filter -> sanity
t("full filter, no search", decl_filter([]))
# search by article
t("article=фильтр", decl_filter([{"column": "productIdentificationArticle", "search": "фильтр"}]))
t("name=фильтр", decl_filter([{"column": "productIdentificationName", "search": "фильтр"}]))
print("done", flush=True)
