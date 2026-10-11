import fsa_api

def filt(search):
    return {"status": [], "columnsSearch": search, "idDeclType": [],
            "idCertObjectType": [], "idProductType": [], "idProductOrigin": [],
            "idGroup": [], "idApplicantType": [],
            "appDate": {"minDate": "", "maxDate": ""}}

cs = [{"column": "productIdentificationArticle", "search": "фильтр"}]
for base in ("/api/v1/rds", "/api/v1/srd", "/api/v1/rss"):
    for ep in ("/common/applications/get", "/common/applications"):
        for label, f in (("empty", filt([])), ("art", filt(cs))):
            try:
                st, res = fsa_api._call("POST", base+ep,
                    {"size": 3, "page": 0, "filter": f,
                     "columnsSort": [{"column": "id", "sort": "ASC"}]})
            except Exception as e:
                print(f"{base+ep} [{label}]: ERR {str(e)[:40]}"); continue
            tot = res.get("total") if isinstance(res, dict) else str(res)[:40]
            print(f"{base+ep} [{label}]: {st} total={tot}", flush=True)
print("done", flush=True)
