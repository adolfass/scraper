#!/usr/bin/env python3
"""Does a brand-wide crawl recover no-article codes via detail annexes?"""
import json, time
import pipeline, fsa_api


def search(col, q, page=0, size=100):
    last = None
    for att in range(5):
        try:
            st, res = fsa_api.search_certificates(
                page=page, size=size,
                columns_sort=[{"column": "id", "sort": "ASC"}],
                columns_search=[{"column": col, "search": q}])
            if st == 200:
                return res
            last = f"HTTP{st}"
        except Exception as e:
            last = str(e)[:60]
        time.sleep(2 * (att + 1))
    print("  search failed:", last, flush=True)
    return {"total": 0, "items": []}


# brands with few certs, plus one no-candidate code each
cases = [("Hyundai/Kia", "0k9b467070h"), ("AUTOGUR", "agft124")]
for brand, code in cases:
    res = search("manufacterName", brand)
    total = res.get("total", 0)
    print(f"=== {brand}: {total} certs ===", flush=True)
    items = res.get("items", [])
    ids = [it.get("id") for it in items]
    # page the rest if needed
    page = 1
    while len(ids) < total and page <= 50:
        res2 = search("manufacterName", brand, page=page)
        ii = res2.get("items", [])
        if not ii:
            break
        ids += [it.get("id") for it in ii]
        page += 1
    print(f"  collected ids: {len(ids)}", flush=True)
    found = False
    for i, cid in enumerate(ids[:40], 1):
        try:
            det = pipeline.get_cert(cid)
        except BaseException as e:
            print("  fetch fail", cid, str(e)[:40], flush=True)
            continue
        blob = json.dumps(det, ensure_ascii=False).lower()
        if code in blob:
            print(f"  FOUND {code} in cert {cid}", flush=True)
            found = True
        if i % 10 == 0:
            print(f"  checked {i}/{len(ids)}", flush=True)
    print(f"  result: {code} {'FOUND' if found else 'not found in detail'}",
          flush=True)
print("done", flush=True)
