#!/usr/bin/env python3
"""Recovery test: scan ALL certs of a few brands, look for 'missing' codes
in their detail annexes. Estimates whether brand+detail crawl can recover
codes that article-search misses."""
import openpyxl, os, re, time, json
from collections import defaultdict
import pipeline, fsa_api

cand = defaultdict(set)
crev = re.compile(r"[;,\s]")
for path in (pipeline.PROBE_LOG, "ip_probe_log.jsonl"):
    if not os.path.exists(path):
        continue
    for rec in pipeline.load_jsonl(path, key="p").values():
        for m in rec.get("matches", []):
            c, rid = m[0], m[1]
            rule = m[2] if len(m) > 2 else "t"
            if rule != "t" and not crev.search(c):
                continue
            cand[c].add(rid)

wb = openpyxl.load_workbook("/Users/mac/Downloads/Итоговый ИП.xlsx",
                            read_only=True, data_only=True)
ws = wb["Лист1"]
by_brand = defaultdict(set)
for r in ws.iter_rows(values_only=True):
    brand = str(r[0] or "").strip()
    code = str(r[1] or "").strip().lower()
    if brand and code and not cand.get(code):
        by_brand[brand.lower()].add(code)
wb.close()


def search(col, q, page=0, size=100):
    for att in range(6):
        try:
            st, res = fsa_api.search_certificates(
                page=page, size=size,
                columns_sort=[{"column": "id", "sort": "ASC"}],
                columns_search=[{"column": col, "search": q}])
            if st == 200:
                return res
        except Exception:
            pass
        time.sleep(2 * (att + 1))
    return {"total": 0, "items": []}


# pick brands with a modest cert count
brands = sorted(by_brand, key=lambda b: len(by_brand[b]))
picks = []
for b in brands:
    res = search("manufacterName", b, size=1)
    total = res.get("total", 0)
    if 3 <= total <= 60:
        picks.append((b, total, by_brand[b]))
    if len(picks) >= 5:
        break

print("brands to scan:", [(b, t, len(c)) for b, t, c in picks], flush=True)

for brand, total, codes in picks:
    res = search("manufacterName", brand, page=0, size=100)
    ids = [it.get("id") for it in res.get("items", [])]
    page = 1
    while len(ids) < total and page <= 20:
        r2 = search("manufacterName", brand, page=page, size=100)
        ii = r2.get("items", [])
        if not ii:
            break
        ids += [it.get("id") for it in ii]
        page += 1
    hits = set()
    blob_all = ""
    for cid in ids[:80]:
        try:
            det = pipeline.get_cert(cid)
        except BaseException:
            continue
        blob_all += json.dumps(det, ensure_ascii=False).lower()
    for c in codes:
        if c in blob_all:
            hits.add(c)
    print(f"brand={brand} certs={len(ids)} missing_codes={len(codes)} "
          f"recovered_in_detail={len(hits)} {sorted(hits)[:5]}", flush=True)
    time.sleep(1)
print("done", flush=True)
