#!/usr/bin/env python3
"""Probe the FSA registry for the articles of Итоговый ИП.xlsx.

Reads unique codes from the input file, searches the certificate registry
by article (gentle, resumable) and records:
  ip_search_rows.jsonl - cert summaries INCLUDING brand fields
                         (manufacterName/applicantName/trademark/...)
  ip_probe_log.jsonl   - {"p": code, "matches": [[code, id, rule], ...]}

rule "t" = exact article token, "s" = substring only.
Resume: codes already present in ip_probe_log.jsonl are skipped.

Usage: DELAY=1 .venv/bin/python ip_probe.py
"""
import json, os, re, time

import openpyxl

import pipeline

ROOT = pipeline.ROOT
SRC = "/Users/mac/Downloads/Итоговый ИП.xlsx"
PROBE = os.path.join(ROOT, "ip_probe_log.jsonl")
ROWS = os.path.join(ROOT, "ip_search_rows.jsonl")
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
    s = {k: it.get(k) for k in ("id", "number", "date", "endDate",
                                "idStatus", "certType")}
    for k in BRAND_FIELDS:
        s[k] = it.get(k)
    return s


def main():
    codes = read_codes()
    done = {}
    for rec in pipeline.load_jsonl(PROBE, key="p").values():
        done[rec["p"]] = rec
    # FORCE=1 re-probes every code (used to repair short codes); ONLY_LEN_BELOW
    # restricts the run to codes shorter than N (shallow probes use size=1).
    force = os.environ.get("FORCE", "0") == "1"
    only_below = int(os.environ.get("ONLY_LEN_BELOW", "0") or 0)
    reprobe = os.environ.get("REPROBE_ERRORS", "0") == "1"
    if reprobe:
        # re-attempt only the codes whose latest record carries an error
        todo = [c for c in codes if done.get(c, {}).get("error")]
    elif force:
        todo = list(codes)
    else:
        todo = [c for c in codes if c not in done]
    if only_below:
        todo = [c for c in todo if len(c) < only_below]
    print(f"codes: {len(codes)}, already probed: {len(done)}, "
          f"to probe: {len(todo)} (force={force}, only_below={only_below})",
          flush=True)

    # server-health circuit breaker: if many codes fail in a row the registry
    # is down/sleeping - pause and retry later instead of burning attempts.
    streak_limit = int(os.environ.get("STREAK_LIMIT", "5"))
    cooldown = int(os.environ.get("COOLDOWN", "300"))
    fail_streak = 0

    for i, code in enumerate(todo, 1):
        try:
            total, items, size = pipeline.probe_prefix(code)
            if total > len(items):
                items = pipeline.fetch_all_rows(code, total, have=items,
                                                have_size=size)
                if len(items) >= MAX_PAGES * 100:
                    print(f"  {code}: capped at {len(items)}/{total}", flush=True)
        except pipeline.QueryError as e:
            print(f"  {code}: query error {e}", flush=True)
            pipeline._append(PROBE, {"p": code, "matches": [],
                                     "error": str(e)})
            continue
        except SystemExit:
            # polite() gave up after repeated server stalls.
            fail_streak += 1
            pipeline._consec_fail[0] = 0
            pipeline._backoff[0] = pipeline.BACKOFF_BASE
            if fail_streak >= streak_limit:
                # the registry looks down (or the machine just woke up):
                # do NOT record this code; wait and let a later run retry it.
                print(f"  {code}: server unhealthy ({fail_streak} fails in a "
                      f"row): cooling down {cooldown}s (not recording)",
                      flush=True)
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

        matches, summaries = [], []
        seen = set()
        for it in items:
            rid = it.get("id")
            if rid is None or rid in seen:
                continue
            art = (it.get(pipeline.ARTICLE_COLUMN) or "").lower()
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
    print("probe complete", flush=True)


if __name__ == "__main__":
    main()
