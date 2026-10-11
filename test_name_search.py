#!/usr/bin/env python3
"""Probe: can we find certs for no-article codes via name/brand fields?"""
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
rows = list(ws.iter_rows(values_only=True))
wb.close()

noc = []
seen = set()
for r in rows:
    code = str(r[1] or "").strip().lower()
    if not code or code in seen:
        continue
    seen.add(code)
    if not cand.get(code):
        noc.append((str(r[0] or "").strip(), code, str(r[2] or "").strip()))

print("no-candidate codes:", len(noc), flush=True)


def tot(col, q, size=1):
    try:
        st, res = fsa_api.search_certificates(
            page=0, size=size,
            columns_sort=[{"column": "id", "sort": "ASC"}],
            columns_search=[{"column": col, "search": q}])
        if st == 200:
            return res.get("total", 0), res.get("items", [])
        return f"HTTP{st}", []
    except Exception as e:
        return f"ERR:{str(e)[:30]}", []


sample = noc[:6]
for brand, code, name in sample:
    a, _ = tot("productIdentificationArticle", code)
    n, _ = tot("productIdentificationName", code)
    f, _ = tot("productFullName", code)
    b, _ = tot("manufacterName", brand)
    print(f"{code:14} brand={brand:16} article={a} name={n} fullname={f} brandcerts={b}",
          flush=True)
    time.sleep(0.5)
print("done", flush=True)
