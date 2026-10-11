#!/usr/bin/env python3
"""Are missing codes absent, or just stored with different formatting?"""
import openpyxl, os, re, time, json
from collections import defaultdict, Counter
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
noc = []
seen = set()
for r in ws.iter_rows(values_only=True):
    code = str(r[1] or "").strip().lower()
    if code and code not in seen:
        seen.add(code)
        if not cand.get(code):
            noc.append(code)
wb.close()

# shape stats
sh = Counter()
for c in noc:
    if c.isdigit():
        sh["all_digits"] += 1
    elif c.isalnum():
        sh["alnum"] += 1
    else:
        sh["other"] += 1
    sh["len_" + str(min(len(c), 12))] += 1
print("no-candidate:", len(noc), dict(sh), flush=True)


def search(col, q, size=1):
    for att in range(5):
        try:
            st, res = fsa_api.search_certificates(
                page=0, size=size,
                columns_sort=[{"column": "id", "sort": "ASC"}],
                columns_search=[{"column": col, "search": q}])
            if st == 200:
                return res.get("total", 0)
        except Exception:
            pass
        time.sleep(2 * (att + 1))
    return "ERR"


import random
random.seed(1)
sample = random.sample(noc, 6)
for c in sample:
    clean = re.sub(r"[^0-9a-z]", "", c)
    variants = {c, clean}
    if clean.isdigit() and len(clean) > 1:
        variants.add(clean.lstrip("0"))
    if len(clean) >= 6:
        variants.add(clean[:6])
        variants.add(clean[:5])
    out = {}
    for v in variants:
        if len(v) < 2:
            continue
        out[v] = search("productIdentificationArticle", v)
        time.sleep(0.4)
    print(f"  {c:16} -> {out}", flush=True)
print("done", flush=True)
