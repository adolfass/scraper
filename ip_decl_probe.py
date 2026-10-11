#!/usr/bin/env python3
"""Probe the FSA DECLARATIONS registry (rds) for the articles of the price list.

The declarations registry is a separate register from certificates: many
auto-parts are DECLARED rather than certified, so they are absent from the
certificate scan and can only be found here.

Reads unique codes from the input file, searches the declarations registry by
article (gentle, resumable) and records:
  ip_decl_rows.jsonl  - declaration summaries INCLUDING brand fields
                        (manufacterName/applicantName/trademark/...)
  ip_decl_probe_log.jsonl - {"p": code, "matches": [[code, id, rule], ...]}

rule "t" = exact article token, "s" = substring only.
Resume: codes already present in ip_decl_probe_log.jsonl are skipped.

Usage: DELAY=1 .venv/bin/python ip_decl_probe.py
"""
import json
import os
import time

import openpyxl

import pipeline
import fsa_api

ROOT = pipeline.ROOT
SRC = "/Users/mac/Downloads/Итоговый ИП.xlsx"
PROBE = os.path.join(ROOT, "ip_decl_probe_log.jsonl")
ROWS = os.path.join(ROOT, "ip_decl_rows.jsonl")
ARTICLE_COLUMN = fsa_api.DECL_ARTICLE_COLUMN
PAGE = 100
MAX_PAGES = 50          # runaway guard: <=5000 items per code

BRAND_FIELDS = ("manufacterName", "applicantName",
                "productIdentificationTrademark",
                "productIdentificationName", "productFullName")


def read_codes():
    wb = openpyxl.load_workbook(SRC, read_only=True, data_only=True)
    ws = wb["Лист1"]
    codes = {}
    for r in ws.iter_rows(values_only=True):
        c = str(r[1] or "").strip().lower() if r[1] is not None else ""
        if c:
            codes[c] = codes.get(c, 0) + 1
    wb.close()
    return codes


def summary(it):
    s = {"id": it.get("id"), "number": it.get("number"),
         "date": it.get("declDate"), "endDate": it.get("declEndDate"),
         "idStatus": it.get("idStatus"),
         "certType": it.get("declType") or it.get("declObjectType") or "",
         "tnved": it.get("productIdentificationOkpdTnved") or "",
         "article": it.get(ARTICLE_COLUMN) or "",
         "src": "decl"}
    for k in BRAND_FIELDS:
        s[k] = it.get(k)
    return s


def fetch_decl_rows(code):
    """Page through all declarations whose article contains `code`."""
    items = []
    for page in range(MAX_PAGES):
        res = pipeline.search_decl(code, page, PAGE)
        batch = res.get("items") or []
        items.extend(batch)
        if len(batch) < PAGE:
            break
    seen, out = set(), []
    for it in items:
        rid = it.get("id")
        if rid is None or rid in seen:
            continue
        seen.add(rid)
        out.append(it)
    return out


def main():
    codes = read_codes()
    restrict = os.environ.get("RESTRICT_TO", "")
    if restrict:
        with open(restrict, encoding="utf-8") as f:
            rs = {ln.strip().lower() for ln in f if ln.strip()}
        codes = {c: n for c, n in codes.items() if c in rs}
        print(f"restricted to {len(codes)} codes from {restrict}", flush=True)
    done = pipeline.load_jsonl(PROBE, key="p")
    force = os.environ.get("FORCE", "0") == "1"
    reprobe = os.environ.get("REPROBE_ERRORS", "0") == "1"
    if reprobe:
        todo = [c for c in codes if done.get(c, {}).get("error")]
    elif force:
        todo = list(codes)
    else:
        todo = [c for c in codes if c not in done]
    print(f"codes: {len(codes)}, already probed: {len(done)}, to probe: {len(todo)}",
          flush=True)

    streak_limit = int(os.environ.get("STREAK_LIMIT", "5"))
    cooldown = int(os.environ.get("COOLDOWN", "300"))
    fail_streak = 0

    for i, code in enumerate(todo, 1):
        try:
            items = fetch_decl_rows(code)
        except pipeline.QueryError as e:
            print(f"  {code}: query error {e}", flush=True)
            pipeline._append(PROBE, {"p": code, "matches": [], "error": str(e)})
            continue
        except SystemExit:
            fail_streak += 1
            pipeline._consec_fail[0] = 0
            pipeline._backoff[0] = pipeline.BACKOFF_BASE
            if fail_streak >= streak_limit:
                print(f"  {code}: server unhealthy ({fail_streak} in a row): "
                      f"cooling down {cooldown}s (not recording)", flush=True)
                time.sleep(cooldown)
                fail_streak = 0
                continue
            print(f"  {code}: server gave up, recording error (retry later)",
                  flush=True)
            pipeline._append(PROBE, {"p": code, "matches": [],
                                     "error": "gaveup"})
            continue
        except Exception as e:
            print(f"  {code}: failed {e}", flush=True)
            pipeline._append(PROBE, {"p": code, "matches": [],
                                     "error": f"{type(e).__name__}: {e}"})
            continue
        fail_streak = 0

        matches, summaries, seen = [], [], set()
        for it in items:
            rid = it.get("id")
            if rid is None or rid in seen:
                continue
            art = (it.get(ARTICLE_COLUMN) or "").lower()
            if not art or code not in art:
                continue
            toks = set(pipeline.TOKEN_SPLIT.split(art)) - {""}
            rule = "t" if code in toks else "s"
            seen.add(rid)
            matches.append([code, rid, rule])
            summaries.append(summary(it))
        pipeline._append(PROBE, {"p": code, "matches": matches})
        for s in summaries:
            pipeline._append(ROWS, s)
        if i % 25 == 0:
            print(f"  probed {i}/{len(todo)} ({code}: {len(matches)} matches)",
                  flush=True)
    print("decl probe complete", flush=True)


if __name__ == "__main__":
    main()
