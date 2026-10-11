#!/usr/bin/env python3
"""Merge peer scan state files into the main ones (run AFTER scans stop).

  probe_log.jsonl   <- + probe_log_b.jsonl, probe_log_c.jsonl
  search_rows.jsonl <- + search_rows_b.jsonl, search_rows_c.jsonl

Dedup keys: probe records by "p" (matches are unioned for duplicate keys,
so pairs found independently by different workers are kept), summaries by
"id".  Files are rewritten atomically (tmp + replace).
"""
import json
import os
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
PEER_PROBE = ["probe_log_b.jsonl", "probe_log_c.jsonl"]
PEER_ROWS = ["search_rows_b.jsonl", "search_rows_c.jsonl"]


def union_matches(dst, src):
    seen = {(m[0], str(m[1])) for m in dst.get("matches", [])}
    for m in src.get("matches", []):
        if (m[0], str(m[1])) not in seen:
            dst.setdefault("matches", []).append(m)
            seen.add((m[0], str(m[1])))


def load(path, key):
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            k = r.get(key)
            if k is None:
                continue
            if k in out:
                union_matches(out[k], r)     # keep pairs from both occurrences
            else:
                out[k] = r
    return out


def dump_atomic(path, records):
    d = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".merge_", suffix=".jsonl")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def merge(main_name, peers, key):
    main = load(os.path.join(ROOT, main_name), key)
    base = len(main)
    added = 0
    for p in peers:
        for k, r in load(os.path.join(ROOT, p), key).items():
            if k not in main:
                main[k] = r
                added += 1
            else:
                before = len(main[k].get("matches", []))
                union_matches(main[k], r)
                added += len(main[k].get("matches", [])) - before
    dump_atomic(os.path.join(ROOT, main_name), list(main.values()))
    print(f"{main_name}: {base} + {added} -> {len(main)} records", flush=True)


if __name__ == "__main__":
    merge("probe_log.jsonl", PEER_PROBE, "p")
    merge("search_rows.jsonl", PEER_ROWS, "id")
    print("merge complete", flush=True)
