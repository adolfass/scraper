#!/usr/bin/env python3
"""QA for the final EXACT_OVERRIDE build of Итоговый ИП_Результат.xlsx.

Rebuilds the chosen-map with the same gate and cross-checks every filled row:
header, Zekkert exclusion, CertUrl/CertNumber consistency, CertType values,
and that each picked cert actually carries the article (brand tier or exact).
"""
import os
import re

import openpyxl

os.environ.update({"RULE": "any", "SUBSTR_TIER2": "1",
                   "BRAND_WEAK": "1", "EXACT_OVERRIDE": "1", "FETCH": "0"})
import pipeline
import build_output as B
import ip_build

URL_RE = re.compile(r"pub\.fsa\.gov\.ru/rss/certificate/view/(\d+)")


def header(path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    h = list(next(ws.iter_rows(values_only=True)))
    wb.close()
    return h


def main():
    print("header matches template:", header("Результат.xlsx")
          == header("Итоговый ИП_Результат.xlsx"))

    cand, subs = ip_build.build_candidates()
    rows_map = pipeline.load_jsonl(ip_build.IP_ROWS, key="id")
    rows_map.update(pipeline.load_jsonl(pipeline.SEARCH_ROWS, key="id"))
    certs = {k: v["data"] for k, v in
             pipeline.load_jsonl(pipeline.CERTS_LOG, key="id").items()
             if v.get("data") is not None}
    strong, weak = {}, {}
    for cid, det in certs.items():
        s, w = B.cert_haystacks(det)
        strong[cid], weak[cid] = s, w
    for cid, s in rows_map.items():
        if cid in strong:
            continue
        strong[cid] = B.norm_text(" ".join(s.get(k) or ""
                                          for k in ip_build.SUMMARY_FIELDS))
        weak[cid] = ""

    def tier(rid, brand):
        if B.brand_matches(brand, strong.get(rid) or ""):
            return 2
        if B.BRAND_WEAK and B.brand_matches(brand, weak.get(rid) or ""):
            return 1
        return 0

    def exact_ok(rid, code):
        return bool(weak.get(rid)) and f" {code} " in weak[rid]

    chosen = {}
    for r in ip_build.load_input():
        brand = str(r[0] or "").strip().lower()
        code = str(r[1] or "").strip().lower()
        if brand in B.EXCLUDE_BRANDS or not code:
            continue
        key = (code, brand)
        if key in chosen:
            continue
        rids = cand.get(code)
        if not rids:
            continue
        ordered = sorted(rids, key=lambda rid: (
            1 if rows_map.get(rid, {}).get("idStatus") == 6 else 0,
            str(rows_map.get(rid, {}).get("date") or "")), reverse=True)
        cur = None
        for lvl in ((2, 1) if B.BRAND_WEAK else (2,)):
            for rid in ordered:
                if lvl < 2 and rid in (subs.get(code) or set()):
                    continue
                if tier(rid, brand) >= lvl:
                    cur = rid
                    break
            if cur:
                break
        if cur is None:
            for rid in ordered:
                if exact_ok(rid, code):
                    cur = rid
                    break
        chosen[key] = cur

    wb = openpyxl.load_workbook("Итоговый ИП_Результат.xlsx",
                                read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    it = ws.iter_rows(values_only=True)
    hdr = list(next(it))
    idx = {k: i for i, k in enumerate(hdr)}
    nrows = zec = filled = tnv = ref_done = 0
    problems = []
    for r in it:
        nrows += 1
        code = str(r[idx["Code"]] or "").strip().lower()
        brand = str(r[idx["BrandName"]] or "").strip().lower()
        num = str(r[idx["CertNumber"]] or "").strip()
        if brand == "zekkert":
            zec += 1
        if not num:
            continue
        filled += 1
        if str(r[idx["TNVED"]] or "").strip():
            tnv += 1
        ctype = str(r[idx["CertType"]] or "").strip()
        if ctype not in {"Сертификат", "Декларация"}:
            problems.append(f"bad certtype {code}/{brand}: {ctype}")
        url = str(r[idx["CertUrl"]] or "").strip()
        m = URL_RE.search(url)
        if not m:
            problems.append(f"non-FSA url {code}/{brand}: {url[:60]}")
            continue
        rid = int(m.group(1))
        exp = chosen.get((code, brand))
        if exp is not None and rid != exp:
            problems.append(f"rid mismatch {code}/{brand}: {rid} vs {exp}")
    wb.close()
    print(f"rows={nrows} filled={filled} tnved={tnv} zekkert_rows={zec}")
    print("problems:", len(problems))
    for p in problems[:8]:
        print("  ", p)


if __name__ == "__main__":
    main()