#!/usr/bin/env python3
"""Analyse what distinguishes ARTICLES THAT GOT a certificate link.

For every unique article code from the price list we know:
  filled      - >=1 output row for this code carries a CertNumber
  has_cand    - the article was found in the FSA cert registry by substring
  absent      - not found there at all
  blocked     - found, but never passed the brand gate

Then we compare structural features of the codes across the classes to derive
search signatures for the remaining articles.
"""
import json
import os
import re
from collections import Counter, defaultdict

os.environ.setdefault("RULE", "any")
os.environ.setdefault("BRAND_WEAK", "1")
os.environ.setdefault("SUBSTR_TIER2", "1")

import openpyxl

import pipeline
import build_output as B
import ip_build

OUT = os.path.join(ip_build.ROOT, "Итоговый ИП_Результат.xlsx")
SRC = "/Users/mac/Downloads/Итоговый ИП.xlsx"

PREF = "1234567890abcdefghijklmnopqrstuvwxyz"

DIG = re.compile(r"^\d+$")
ALPHA = re.compile(r"^[a-z]+$")
HEXLIKE = re.compile(r"^[0-9a-f]+$")           # pure hex digits
MIX = re.compile(r"^[0-9a-z]+$")
HAS_DASH = re.compile(r"[-/]")
START_DIGIT = re.compile(r"^\d")


def classify_art(art):
    feat = {
        "len": min(len(art), 14),
        "len_bucket": bucket(len(art)),
        "pure_digits": bool(DIG.match(art)),
        "pure_alpha": bool(ALPHA.match(art)),
        "hexlike": bool(HEXLIKE.match(art)) and not DIG.match(art),
        "mixed_alnum": bool(MIX.match(art)) and not DIG.match(art) and not ALPHA.match(art),
        "starts_digit": bool(START_DIGIT.match(art)),
        "has_sep": bool(HAS_DASH.search(art)),
        "p2": art[:2],
        "p4": art[:4],
        "p6": art[:6],
    }
    # digit-heavy numeric classes used by OEM catalogs
    if DIG.match(art):
        n = int(art)
        if len(art) == 7:
            feat["class"] = "num7"
        elif len(art) == 8:
            feat["class"] = "num8"
        elif len(art) == 6:
            feat["class"] = "num6"
        elif len(art) <= 5:
            feat["class"] = "num<=5"
        elif len(art) >= 9:
            feat["class"] = "num>=9"
    elif ALPHA.match(art):
        feat["class"] = "alpha"
    elif len(art) >= 9:
        feat["class"] = "long_mixed>=9"
    elif 6 <= len(art) <= 8:
        feat["class"] = "mixed6-8"
    else:
        feat["class"] = "short_mixed<=5"
    return feat


def bucket(n):
    if n <= 4:
        return "<=4"
    if n <= 6:
        return "5-6"
    if n <= 8:
        return "7-8"
    if n <= 10:
        return "9-10"
    if n <= 12:
        return "11-12"
    return "13+"


def main():
    cand, subs = ip_build.build_candidates()

    wb = openpyxl.load_workbook(OUT, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    it = ws.iter_rows(values_only=True)
    hdr = list(next(it))
    ci = hdr.index("Code")
    bi = hdr.index("BrandName")
    ni = hdr.index("CertNumber")
    filled_codes = set()
    code_brands = defaultdict(set)
    for r in it:
        code = str(r[ci] or "").strip().lower()
        brand = str(r[bi] or "").strip().lower()
        if not code:
            continue
        code_brands[code].add(brand)
        if r[ni] and str(r[ni]).strip():
            filled_codes.add(code)
    wb.close()

    wb = openpyxl.load_workbook(SRC, read_only=True, data_only=True)
    ws = wb["Лист1"]
    code_count = Counter()
    brand_count = Counter()
    for r in ws.iter_rows(values_only=True):
        brand = str(r[0] or "").strip().lower()
        code = str(r[1] or "").strip().lower() if r[1] is not None else ""
        if not code:
            continue
        code_count[code] += 1
        brand_count[brand] += 1
    wb.close()

    # three-way classification
    has_cand = set(cand)
    stats = {"filled": 0, "blocked": 0, "absent": 0}
    cls = {}
    feat_fill = defaultdict(Counter)   # feature -> {value: {class: n}}
    for code in code_count:
        cls_i = "absent"
        if code in filled_codes:
            cls_i = "filled"
        elif code in has_cand:
            cls_i = "blocked"
        stats[cls_i] += 1
        cls[code] = cls_i
        f = classify_art(code)
        for k, v in f.items():
            feat_fill[k][(str(v), cls_i)] += 1

    print(f"unique codes: {len(code_count)}  ->  filled {stats['filled']}, "
          f"blocked {stats['blocked']}, absent {stats['absent']}", flush=True)

    def show_feature(key, top=12, order=None):
        g = defaultdict(Counter)
        for (val, ci), n in feat_fill[key].items():
            g[val][ci] += n
        rows = sorted(g.items(), key=lambda kv: -sum(kv[1].values()))[:top]
        print(f"\n== {key} ==")
        for val, c in rows:
            f = c.get("filled", 0)
            b = c.get("blocked", 0)
            a = c.get("absent", 0)
            share = f / (f + b + a) * 100 if (f + b + a) else 0
            bar = "#" * int(share / 4)
            print(f"  {val!r:16s} n={f+b+a:5d}  filled={f:5d} "
                  f"blocked={b:5d} absent={a:5d}  fill%={share:4.1f} {bar}")

    show_feature("class", top=20)
    show_feature("len_bucket")
    show_feature("p2", top=25)
    show_feature("p4", top=25)

    # brand fill rate
    print("\n== brand fill rate (>=10 rows) ==")
    brand_fill = defaultdict(lambda: [0, 0])   # filled codes, rows
    for code, bl in code_brands.items():
        b_f = code in filled_codes
        for b in bl:
            brand_fill[b][0] += 1 if b_f else 0
            brand_fill[b][1] += 1
    ranked = sorted(brand_fill.items(), key=lambda kv: -kv[1][1])
    print("top by rows:")
    for b, (f, n) in ranked[:18]:
        print(f"  {b!r:22s} rows={n:4d} codes_filled={f:4d}")
    print("worst fill (>=10 rows):")
    for b, (f, n) in sorted(ranked, key=lambda kv: kv[1][0] / max(kv[1][1], 1))[:18]:
        if n >= 10:
            print(f"  {b!r:22s} rows={n:4d} codes_filled={f:4d}")

    json.dump({c: cls[c] for c in code_count},
              open("/tmp/code_classes.json", "w"))


if __name__ == "__main__":
    main()