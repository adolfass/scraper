#!/usr/bin/env python3
"""Fetch cert detail cards for ALL candidate certs (not just chosen ones).

Needed by the brand gate in build_output.py: to re-choose a candidate by
manufacturer match we need each candidate's manufacturer/trademark fields.

Codes whose rows are ALL of an excluded brand (Zekkert) are skipped, so
their exclusive certs are never fetched.  Gentle mode: sequential, DELAY
per request, exponential backoff via pipeline.polite.

Usage: .venv/bin/python fetch_cand_details.py
"""
import json, os, re
from collections import defaultdict

import openpyxl

import pipeline

EXCLUDE_BRANDS = {b.strip().lower()
                  for b in os.environ.get("EXCLUDE_BRANDS", "zekkert").split(",")
                  if b.strip()}


def main():
    cand = defaultdict(set)
    complex_re = re.compile(r"[;,\s]")
    for rec in pipeline.load_jsonl(pipeline.PROBE_LOG, key="p").values():
        for m in rec.get("matches", []):
            code, rid = m[0], m[1]
            rule = m[2] if len(m) > 2 else "t"
            if rule != "t" and not complex_re.search(code):
                continue          # RULE=mix parity with build_output
            cand[code].add(rid)

    # codes that appear on at least one non-excluded row
    wb = openpyxl.load_workbook(os.path.join(pipeline.ROOT, "Исходный.xlsx"),
                                read_only=True, data_only=True)
    ws = wb["PRICE"]
    it = ws.iter_rows(values_only=True)
    hdr = list(next(it))
    ci = hdr.index("Code")
    bi = hdr.index("BrandName")
    live_codes = set()
    for r in it:
        code = str(r[ci]).strip().lower() if r[ci] else ""
        brand = str(r[bi] or "").strip().lower()
        if code and brand not in EXCLUDE_BRANDS:
            live_codes.add(code)
    wb.close()

    need_ids = {c for code, s in cand.items() if code in live_codes for c in s}
    have = {int(k) for k, v in pipeline.load_jsonl(pipeline.CERTS_LOG,
                                                   key="id").items()
            if v.get("data") is not None}
    need = sorted(need_ids - have)
    print(f"live codes: {len(live_codes)}, candidate certs: {len(need_ids)}, "
          f"have: {len(have)}, to fetch: {len(need)}", flush=True)
    for i, cid in enumerate(need, 1):
        try:
            data = pipeline.get_cert(cid)
        except SystemExit:
            raise
        except Exception as e:
            print(f"  cert {cid} failed: {e}", flush=True)
            continue
        pipeline._append(pipeline.CERTS_LOG, {"id": cid, "data": data})
        if i % 25 == 0:
            print(f"  details {i}/{len(need)}", flush=True)
    print("candidate details complete", flush=True)


if __name__ == "__main__":
    main()
