import fsa_api

def filt(search):
    return {"status": [], "columnsSearch": search, "idDeclType": [],
            "idCertObjectType": [], "idProductType": [], "idProductOrigin": [],
            "idGroup": [], "idApplicantType": [],
            "appDate": {"minDate": "", "maxDate": ""}}

paths = ["/api/v1/rds/common/declarations/get",
         "/api/v1/rds/srd/declarations/get",
         "/api/v1/srd/common/declarations/get",
         "/api/v1/srd/declarations/get",
         "/api/v1/rds/common/declarations",
         "/api/v1/rds/srd/declarations",
         "/api/v1/srd/common/declarations"]

cs = [{"column": "productIdentificationArticle", "search": "фильтр"}]
for p in paths:
    for label, f in (("empty", filt([])), ("art", filt(cs))):
        try:
            st, res = fsa_api._call("POST", p, {"size": 3, "page": 0, "filter": f,
                                                 "columnsSort": [{"column": "id", "sort": "ASC"}]})
        except Exception as e:
            print(f"{p} [{label}]: ERR {str(e)[:40]}", flush=True); continue
        tot = res.get("total") if isinstance(res, dict) else str(res)[:40]
        print(f"{p} [{label}]: {st} total={tot}", flush=True)
print("done", flush=True)
