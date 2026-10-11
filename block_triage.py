#!/usr/bin/env python3
"""Triage the "blocked" (found in cert registry, brand gate failed) pairs.

REUSE the exact ip_build gate to rebuild the blocked list, then for each
blocked (brand, code) show the top candidate cert with readable fields so we
can separate legitimately-blocked pairs (foreign/OE manufacturer) from
possible alias/whitelist candidates.
"""
import json
import os
import re
from collections import Counter, defaultdict

import openpyxl

import pipeline
import build_output as B
import ip_build

ENV = {k: v for k, v in {
    "RULE": "any", "SUBSTR_TIER2": "1", "BRAND_WEAK": "1"}.items()}
for k, v in ENV.items():
    os.environ.setdefault(k, v)

OUT = os.path.join(ip_build.ROOT, "Итоговый ИП_Результат.xlsx")


def readable(det):
    d = det or {}
    man = d.get("manufacturer") or {}
    app = d.get("applicant") or {}
    prod = d.get("product") or {}
    idents = prod.get("identifications") or []
    arts = [i.get("article") for i in idents if i.get("article")][:12]
    return {
        "docId": d.get("docId") or d.get("certificateNumber") or d.get("regNumber"),
        "tradeMark": d.get("tradeMark"),
        "manufacturer": man.get("fullName"),
        "applicant": app.get("fullName"),
        "product": prod.get("fullName") or prod.get("name"),
        "articles": arts,
        "reg": d.get("certRegDate"),
        "end": d.get("certEndDate"),
    }


def main():
    cand, subs = ip_build.build_candidates()

    rows_map = pipeline.load_jsonl(ip_build.IP_ROWS, key="id")
    rows_map.update(pipeline.load_jsonl(pipeline.SEARCH_ROWS, key="id"))
    certs = {k: v["data"] for k, v in
             pipeline.load_jsonl(pipeline.CERTS_LOG, key="id").items()
             if v.get("data") is not None}

    strong = {}
    weak = {}
    for cid, det in certs.items():
        s, w = B.cert_haystacks(det)
        strong[cid] = s
        weak[cid] = w
    for cid, s in rows_map.items():
        if cid in strong:
            continue
        strong[cid] = B.norm_text(" ".join(s.get(k) or "" for k in ip_build.SUMMARY_FIELDS))
        weak[cid] = ""

    def tier(rid, brand):
        if B.brand_matches(brand, strong.get(rid) or ""):
            return 2
        if B.BRAND_WEAK and B.brand_matches(brand, weak.get(rid) or ""):
            return 1
        return 0

    rows = ip_build.load_input()
    blocked = defaultdict(list)   # (brand, code) -> candidates
    for r in rows:
        brand = str(r[0] or "").strip().lower() if r[0] is not None else ""
        code = str(r[1] or "").strip().lower() if r[1] is not None else ""
        if brand in B.EXCLUDE_BRANDS or not code:
            continue
        rids = cand.get(code)
        if not rids:
            continue
        ok = any(tier(rid, brand) >= 1 for rid in rids)
        if not ok:
            blocked[(code, brand)].append(sorted(rids))

    st = Counter()
    for (code, brand), groups in blocked.items():
        st[brand] += 1
    print("blocked pairs:", len(blocked), "distinct brands:", len(st))

    out = []
    for (code, brand), groups in sorted(blocked.items(), key=lambda kv: kv[0][1]):
        rid = groups[0][0]   # newest/relevant candidate set, pick first rid
        det = certs.get(rid)
        rd = readable(det) if det else {"docId": str(rid)}
        rd["code"] = code
        rd["brand"] = brand
        # how close is the brand to the candidate at all?
        s = strong.get(rid) or ""
        w = weak.get(rid) or ""
        share = sorted(set(B.brand_variants(brand)) &
                       set(B.norm_text(s + " " + w).split()))
        rd["shared_tokens"] = share[:8]
        rd["tier1"] = tier(rid, brand)
        out.append(rd)

    with open("/tmp/blocked_triage.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    by_brand = Counter(x["brand"] for x in out)
    print("\n== blocked by brand ==")
    for b, n in by_brand.most_common(40):
        print(f"  {b!r:20s} {n}")
    print("\n== examples (top candidate per code, brand grouped) ==")
    shown = 0
    for b in [x for x, _ in by_brand.most_common(12)]:
        print(f"\n-- {b} --")
        cnt = 0
        for x in out:
            if x["brand"] != b or cnt >= 3:
                continue
            cnt += 1
            print(f"  code={x['code']!r} docId={x['docId']!r} "
                  f"tm={str(x['tradeMark'])[:40]!r}")
            print(f"    manufacturer={str(x['manufacturer'])[:70]!r}")
            print(f"    product={str(x['product'])[:80]!r}")
            print(f"    articles={x['articles'][:4]}")
            print(f"    reg={x['reg']} end={x['end']} tier1={x['tier1']} "
                  f"shared={x['shared_tokens'][:5]}")


if __name__ == "__main__":
    main()