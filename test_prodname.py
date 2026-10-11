#!/usr/bin/env python3
"""ProdName confirmation of pure-substring matches (user's triple-match idea)."""
import openpyxl, os, re
from collections import defaultdict, Counter
import pipeline, build_output as B
B.BRAND_WEAK = True

# load probe logs once -> code -> (t_ids, s_ids)
tmap = defaultdict(set); smap = defaultdict(set)
for path in (pipeline.PROBE_LOG, "ip_probe_log.jsonl"):
    if not os.path.exists(path):
        continue
    for code, rec in pipeline.load_jsonl(path, key="p").items():
        for m in rec.get("matches", []):
            (tmap if (m[2] if len(m) > 2 else "t") == "t" else smap)[code].add(m[1])

rows_map = pipeline.load_jsonl(pipeline.SEARCH_ROWS, key="id")
rows_map.update(pipeline.load_jsonl("ip_search_rows.jsonl", key="id"))
certs = {k: v["data"] for k, v in
         pipeline.load_jsonl(pipeline.CERTS_LOG, key="id").items()
         if v.get("data") is not None}
strong = {}; weak = {}
for cid, det in certs.items():
    a, b = B.cert_haystacks(det); strong[cid] = a; weak[cid] = b
SUM = ("manufacterName", "applicantName", "productIdentificationTrademark",
       "productIdentificationName", "productFullName")
for cid, s in rows_map.items():
    if cid in strong:
        continue
    strong[cid] = B.norm_text(" ".join(str(s.get(k)) for k in SUM if s.get(k)))
    weak[cid] = ""


def tier(rid, bn):
    s = strong.get(rid)
    if s is None:
        return 0
    if bn in s:
        return 2
    if B.BRAND_WEAK and bn in (weak.get(rid) or ""):
        return 1
    return 0


def choose(rids, bn):
    for rid in sorted(rids,
                      key=lambda x: (1 if rows_map.get(x, {}).get("idStatus") == 6 else 0,
                                     str(rows_map.get(x, {}).get("date") or "")),
                      reverse=True):
        if tier(rid, bn) >= 1:
            return rid
    return None


wb = openpyxl.load_workbook("/Users/mac/Downloads/Итоговый ИП.xlsx",
                            read_only=True, data_only=True)
ws = wb["Лист1"]
rows = list(ws.iter_rows(values_only=True))
wb.close()

st = Counter(); seen = set()
for r in rows:
    brand = str(r[0] or "").strip(); bl = brand.lower()
    code = str(r[1] or "").strip().lower(); name = str(r[2] or "").strip()
    if bl in B.EXCLUDE_BRANDS or not code or (code, bl) in seen:
        continue
    seen.add((code, bl))
    if tmap.get(code) or not smap.get(code):
        continue                      # only pure-substring codes
    bn = B.norm_text(bl)
    cid = choose(smap[code], bn)
    if cid is None:
        st["only_s_brand_blocked"] += 1
        continue
    st["only_s_matched"] += 1
    h = strong.get(cid, "")
    toks = set(w for w in re.findall(r"[0-9a-zа-яё]{5,}", B.norm_text(name)))
    if not toks:
        st["  prodname_short"] += 1
    else:
        hit = sum(1 for w in toks if w in h)
        if hit == 0:
            st["  prodname_no_overlap"] += 1
        elif hit < len(toks):
            st["  prodname_partial"] += 1
        else:
            st["  prodname_full"] += 1
print("pure-substring (code,brand) pairs:")
for k, v in st.items():
    print(f"  {k}: {v}")
