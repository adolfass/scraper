#!/usr/bin/env python3
"""Count per-brand gap: (code, brand) pairs whose codes have FSA certificate
candidates but none passed the brand gate - the alias-addressable deficit."""
import json, os, re
from collections import Counter, defaultdict

import openpyxl

import pipeline
import build_output as B
import ip_build

ROOT = pipeline.ROOT
SRC = "/Users/mac/Downloads/Итоговый ИП.xlsx"


def main():
    print(f"RULE={B.RULE} BRAND_WEAK={B.BRAND_WEAK} "
          f"SUBSTR_TIER2={os.environ.get('SUBSTR_TIER2','0')}", flush=True)
    cand, subs = ip_build.build_candidates()

    rows_map = pipeline.load_jsonl(pipeline.SEARCH_ROWS, key="id")
    rows_map.update(pipeline.load_jsonl(ip_build.IP_ROWS, key="id"))
    certs = {k: v["data"] for k, v in
             pipeline.load_jsonl(pipeline.CERTS_LOG, key="id").items()
             if v.get("data") is not None}
    print(f"certs detail: {len(certs)}, summaries: {len(rows_map)}, "
          f"codes with cand: {len(cand)}", flush=True)

    strong, weak = {}, {}
    for cid, det in certs.items():
        s, w = B.cert_haystacks(det)
        strong[cid], weak[cid] = s, w
    for cid, s in rows_map.items():
        if cid in strong:
            continue
        parts = [s.get(k) for k in ip_build.SUMMARY_FIELDS if s.get(k)]
        strong[cid] = B.norm_text(" ".join(parts))
        weak[cid] = ""

    _cache = {}

    def tier(rid, brand_n):
        key = (rid, brand_n)
        t = _cache.get(key, -1)
        if t == -1:
            s, w = strong.get(rid), weak.get(rid)
            if s is None:
                t = 0
            elif B.brand_matches(brand_n, s):
                t = 2
            elif B.BRAND_WEAK and B.brand_matches(brand_n, w or ""):
                t = 1
            else:
                t = 0
            _cache[key] = t
        return t

    def choose_gated(rids, brand_n, subs=None):
        subs = subs or set()
        def k(rid):
            r = rows_map.get(rid, {})
            return (1 if r.get("idStatus") == 6 else 0, str(r.get("date") or ""))
        ordered = sorted(rids, key=k, reverse=True)
        for lvl in ((2, 1) if B.BRAND_WEAK else (2,)):
            for rid in ordered:
                if lvl < 2 and rid in subs:
                    continue
                if tier(rid, brand_n) >= lvl:
                    return rid
        return None

    wb = openpyxl.load_workbook(SRC, read_only=True, data_only=True)
    ws = wb["Лист1"]
    blocked = defaultdict(set)      # raw brand -> set of codes
    examples = {}                    # raw brand -> first (code, rids)
    n_rows = 0
    for r in ws.iter_rows(values_only=True):
        brand_raw = str(r[0] or "").strip()
        code = str(r[1] or "").strip().lower() if r[1] is not None else ""
        if not code or not brand_raw:
            continue
        n_rows += 1
        bl = brand_raw.lower()
        if bl in B.EXCLUDE_BRANDS:
            continue
        rids = cand.get(code)
        if not rids:
            continue
        if choose_gated(rids, B.norm_text(bl), subs.get(code)) is None:
            blocked[brand_raw].add(code)
            if brand_raw not in examples:
                examples[brand_raw] = (code, rids)
    wb.close()
    print(f"rows seen: {n_rows}", flush=True)
    ranked = sorted(blocked.items(),
                    key=lambda kv: (-len(kv[1]), kv[0].lower()))
    tot = sum(len(v) for v in blocked.values())
    print(f"blocked (code,brand) pairs: {tot}, across {len(blocked)} brands\n")
    for b, codes in ranked[:45]:
        c, rids = examples[b]
        print(f"{len(codes):4d}  {b!r:24s} e.g. code={c!r} n_rids={len(rids)}")
    json.dump({b: {"codes": sorted(v),
                   "example_code": examples[b][0],
                   "rids": sorted(examples[b][1])}
               for b, v in blocked.items()},
              open("/tmp/blocked_brands.json", "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()