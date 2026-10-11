#!/usr/bin/env python3
"""Blocked pairs: how many would fill under an EXACT-ARTICLE override?

For each blocked (brand, code) pair we check every candidate cert: does the
code appear as an EXACT whitespace token in the cert's identification/annex
text (weak haystack)?  If yes -> the certificate genuinely names this article,
the only obstacle is the brand gate.

Output: /tmp/blocked_exact.json + summary; prints examples per brand.
"""
import json
import os
import re
from collections import Counter, defaultdict

import pipeline
import build_output as B
import ip_build

for k, v in {"RULE": "any", "SUBSTR_TIER2": "1", "BRAND_WEAK": "1"}.items():
    os.environ.setdefault(k, v)

TOK = re.compile(r"[0-9a-z]+")


def has_exact_tok(hay_norm, code):
    """Exact token check: normalized text has tokens separated by single
    spaces, so ' code ' as a substring == exact whitespace token."""
    return f" {code} " in hay_norm


def main():
    cand, subs = ip_build.build_candidates()
    rows_map = pipeline.load_jsonl(ip_build.IP_ROWS, key="id")
    rows_map.update(pipeline.load_jsonl(pipeline.SEARCH_ROWS, key="id"))
    certs = {k: v["data"] for k, v in
             pipeline.load_jsonl(pipeline.CERTS_LOG, key="id").items()
             if v.get("data") is not None}

    weak = {}
    strong = {}
    for cid, det in certs.items():
        s, w = B.cert_haystacks(det)
        strong[cid] = s
        weak[cid] = w
    for cid, s in rows_map.items():
        if cid in strong:
            continue
        strong[cid] = B.norm_text(" ".join(s.get(k) or "" for k in ip_build.SUMMARY_FIELDS))
        weak[cid] = ""

    def gate_ok(rid, brand):
        if B.brand_matches(brand, strong.get(rid) or ""):
            return True
        if B.BRAND_WEAK and B.brand_matches(brand, weak.get(rid) or ""):
            return True
        return False

    rows = ip_build.load_input()
    blocked = defaultdict(set)     # (code, brand) -> rids (whole gate failed)
    for r in rows:
        brand = str(r[0] or "").strip().lower() if r[0] is not None else ""
        code = str(r[1] or "").strip().lower() if r[1] is not None else ""
        if brand in B.EXCLUDE_BRANDS or not code:
            continue
        rids = cand.get(code)
        if not rids:
            continue
        if not any(gate_ok(rid, brand) for rid in rids):
            blocked[(code, brand)].update(rids)

    print(f"blocked pairs: {len(blocked)}", flush=True)

    # exact-article candidates per blocked pair
    exact = {}                 # (code,brand) -> list of (rid, docId, manufacturer, trademark)
    for (code, brand), rids in blocked.items():
        hits = []
        for rid in rids:
            w = weak.get(rid)
            if w and has_exact_tok(w, code):
                det = certs.get(rid) or {}
                man = (det.get("manufacturer") or {}).get("fullName")
                hits.append((rid, det.get("docId"), man,
                             det.get("tradeMark"),
                             rows_map.get(rid, {}).get("date")))
        if hits:
            exact[(code, brand)] = hits

    print(f"blocked pairs with EXACT article in a candidate: {len(exact)} "
          f"({len(exact)/len(blocked)*100:.1f}%)", flush=True)

    by_brand = Counter(brand for (_, brand) in exact)
    print("\n== exact-candidate blocked pairs by brand (rows potentially fillable) ==")
    for b, n in by_brand.most_common(45):
        print(f"  {b!r:22s} {n}")

    json.dump({f"{code}|{brand}": hits for (code, brand), hits in sorted(exact.items())},
              open("/tmp/blocked_exact.json", "w"), ensure_ascii=False, indent=1)

    print("\n== examples ==")
    shown = 0
    for (code, brand), hits in sorted(exact.items()):
        if shown >= 25:
            break
        shown += 1
        rid, docid, man, tm, date = hits[0]
        s = strong.get(rid) or ""
        print(f"  {brand!r} {code!r} <- rid={rid} docId={str(docid)[:40]!r} "
              f"date={date}")
        print(f"      mfr={str(man)[:60]!r} tm={str(tm)[:40]!r}")


if __name__ == "__main__":
    main()