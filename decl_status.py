#!/usr/bin/env python3
"""Snapshot of the declarations scan: progress, throughput, ETA, fill estimate."""
import json
import os
import subprocess
import time
from collections import Counter

import pipeline

ROOT = pipeline.ROOT
PROBE = os.path.join(ROOT, "ip_decl_probe_log.jsonl")
ROWS = os.path.join(ROOT, "ip_decl_rows.jsonl")
CERT_PROBE = os.path.join(ROOT, "ip_probe_log.jsonl")
PREV = "/tmp/decl_status_prev.json"
TOTAL_DEFAULT = 3877
SCOPE = "/tmp/decl_scope.txt"


def total_codes():
    v = os.environ.get("DECL_TOTAL")
    if v:
        return int(v)
    if os.path.exists(SCOPE):
        try:
            return sum(1 for _ in open(SCOPE, encoding="utf-8"))
        except Exception:
            pass
    return TOTAL_DEFAULT


def load_key(path):
    return pipeline.load_jsonl(path, key="p") if os.path.exists(path) else {}


def proc_alive():
    try:
        return subprocess.check_output(["pgrep", "-f", "ip_decl_probe.py"],
                                       stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return ""


def main():
    log = load_key(PROBE)
    cert = load_key(CERT_PROBE)
    rows = pipeline.load_jsonl(ROWS, key="id") if os.path.exists(ROWS) else {}

    done = len(log)
    TOTAL = total_codes()
    errs = sum(1 for r in log.values() if r.get("error"))
    mk = sum(len(r.get("matches", [])) for r in log.values())
    codes_hit = {c for c, r in log.items() if r.get("matches")}
    rules = Counter(m[2] for r in log.values() for m in r.get("matches", [])
                    if len(m) > 2)
    cert_codes = {c for c, r in cert.items() if r.get("matches")}
    decl_only = codes_hit - cert_codes

    now = time.time()
    prev = {}
    if os.path.exists(PREV):
        try:
            prev = json.load(open(PREV))
        except Exception:
            prev = {}
    rate = eta = None
    if prev.get("t") and prev.get("done") is not None and now > prev["t"]:
        dt = now - prev["t"]
        ddone = done - prev["done"]
        if dt > 5 and ddone >= 0:
            rate = ddone / dt
            if rate > 0:
                eta = (TOTAL - done) / rate
    json.dump({"t": now, "done": done}, open(PREV, "w"))

    pct = done / TOTAL * 100 if TOTAL else 0
    print(f"[{time.strftime('%H:%M:%S')}] declarations scan")
    print(f"  codes done : {done}/{TOTAL} ({pct:.1f}%)   errors: {errs}")
    print(f"  rows stored: {len(rows)}")
    print(f"  codes with >=1 decl match : {len(codes_hit)}")
    print(f"  match pairs: {mk}  rules: {dict(rules)}")
    print(f"  decl matches NOT in certificate scan (net-new codes): {len(decl_only)}")
    if rate:
        print(f"  rate: {rate*60:.1f} codes/min   ETA: {eta/60:.0f} min" if eta
              else f"  rate: {rate*60:.1f} codes/min")
    print(f"  process alive: {bool(proc_alive())}")


if __name__ == "__main__":
    main()
