import fsa_api

def req(cs):
    return {"size": 5, "page": 0, "count": 0,
            "filter": {"status": [], "idDeclType": [], "idCertObjectType": [],
                       "idProductType": [], "idGroupRU": [], "idGroupEEU": [],
                       "idTechReg": [], "idApplicantType": [],
                       "regDate": {"minDate": "", "maxDate": ""},
                       "endDate": {"minDate": "", "maxDate": ""},
                       "columnsSearch": cs},
            "columnsSort": []}

def t(desc, cs):
    try:
        st, res = fsa_api._call("POST", "/api/v1/rds/common/declarations/get", req(cs))
    except Exception as e:
        print(f"{desc}: ERR {str(e)[:50]}", flush=True); return
    if isinstance(res, dict):
        items = res.get("items") or []
        print(f"{desc}: {st} total={res.get('total')} n={len(items)}", flush=True)
        if st == 200 and items:
            it = items[0]
            print("   ", {k: it.get(k) for k in ("declNumber", "declDate",
                  "manufacterName", "productIdentificationArticle",
                  "productIdentificationName")}, flush=True)
    else:
        print(f"{desc}: {st} {str(res)[:70]}", flush=True)

t("empty", [])
t("art=фильтр", [{"column": "productIdentificationArticle", "search": "фильтр"}])
t("art=LR000695", [{"column": "productIdentificationArticle", "search": "LR000695"}])
t("fullname=фильтр", [{"column": "productFullName", "search": "фильтр"}])
t("manuf=Cummins", [{"column": "manufacterName", "search": "Cummins"}])
print("done", flush=True)
