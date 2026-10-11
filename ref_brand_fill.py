#!/usr/bin/env python3
"""Fill empty rows using the BRAND->certificate mapping learned from Результат.xlsx.

The reference file attaches one (or a few) certificates to a whole brand group
(e.g. all LYNXAUTO articles -> one cert).  We mine that mapping and apply it to
rows whose exact (Code,BrandName) was not already carried over.

Env:
  REF_IN    reference workbook (default Результат.xlsx)
  BR_IN     input workbook (default Итоговый ИП_Результат_annex.xlsx)
  BR_OUT    output workbook (default Итоговый ИП_Результат_brand.xlsx)
  BR_ONLY_MISSING=1  only rows whose brand is NOT already represented
"""
import json
import os
import re
from collections import Counter, defaultdict

import openpyxl

REF_IN = os.environ.get("REF_IN", "Результат.xlsx")
BR_IN = os.environ.get("BR_IN", "Итоговый ИП_Результат_annex.xlsx")
BR_OUT = os.environ.get("BR_OUT", "Итоговый ИП_Результат_brand.xlsx")


def build_ref_map():
    wb = openpyxl.load_workbook(REF_IN, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    it = ws.iter_rows(values_only=True)
    h = list(next(it))
    bi, ni, ui, ti, yi = (h.index(x) for x in
                          ("BrandName", "CertNumber", "CertUrl", "TNVED", "CertType"))
    cnt = defaultdict(Counter)
    info = {}
    for r in it:
        b = str(r[bi] or "").strip().lower()
        c = str(r[ni] or "").strip()
        if not b or not c:
            continue
        cnt[b][c] += 1
        info.setdefault((b, c), (r[ui], r[ti], r[yi]))
    wb.close()
    # best cert per brand = most frequent
    best = {b: cc.most_common(1)[0][0] for b, cc in cnt.items()}
    return cnt, best, info


def split_parts(b):
    return [p.strip() for p in re.split(r"[/,&]+", b) if p.strip()]


def best_for(b, cnt, best):
    """Brand key -> certificate.  Falls back to split parts for compound
    labels such as "hyundai/kia" (pick the part the reference covers most)."""
    if b in best:
        return b, best[b]
    hits = [(len(cnt[p]), p) for p in split_parts(b) if p in cnt]
    if hits:
        p = max(hits)[1]
        return p, best[p]
    return None, None


def main():
    cnt, best, info = build_ref_map()
    print(f"reference brands with certs: {len(best)}", flush=True)

    wb = openpyxl.load_workbook(BR_IN, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    it = ws.iter_rows(values_only=True)
    header = list(next(it))
    idx = {h: i for i, h in enumerate(header)}
    bi, ni = idx["BrandName"], idx["CertNumber"]
    stat = Counter()
    rows = []
    audit = []
    for r in it:
        row = list(r)
        b = str(row[bi] or "").strip().lower()
        empty = not (row[ni] and str(row[ni]).strip())
        key, c = best_for(b, cnt, best) if empty else (None, None)
        if c:
            url, tnved, ctype = info.get((key, c), (None, None, None))
            row[idx["CertNumber"]] = c
            row[idx["CertUrl"]] = url or ""
            row[idx["TNVED"]] = tnved or ""
            row[idx["CertType"]] = ctype or ""
            stat["filled"] += 1
            # optional provenance note (off by default so the sheet matches
            # the reference format exactly)
            if os.environ.get("BR_NOTE") == "1":
                ci = idx.get("Commentary")
                if ci is not None and not (row[ci] and str(row[ci]).strip()):
                    row[ci] = "групповой (бренд)"
                    stat["commented"] += 1
            audit.append([str(row[idx["Code"]]), b, c, url, tnved, ctype])
        row = ["" if v is None else v for v in row]
        if len(row) < len(header):
            row += [""] * (len(header) - len(row))
        rows.append(row)
    wb.close()

    owb = openpyxl.Workbook(write_only=True)
    ows = owb.create_sheet("PRICE")
    ows.append(header)
    for r in rows:
        ows.append(r)
    owb.save(BR_OUT)
    print("stats:", dict(stat), flush=True)
    print(f"written {BR_OUT} ({len(rows)} rows)", flush=True)


if __name__ == "__main__":
    main()
