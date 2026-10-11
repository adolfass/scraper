#!/usr/bin/env python3
"""Union of all scan state into *_all.jsonl COPIES.

Unlike merge_state.py (which rewrites the main files and must only run AFTER
all scans stop), this writes separate probe_log_all.jsonl / search_rows_all.jsonl
so extra consumers (details, build) can see every worker's pairs while worker A
is still appending to probe_log.jsonl.

Run repeatedly; cheap and idempotent.
"""
import merge_state as ms
import os

ROOT = ms.ROOT


def build(main_name, peers, key, out_name):
    out = ms.load(os.path.join(ROOT, main_name), key)
    for p in peers:
        for k, r in ms.load(os.path.join(ROOT, p), key).items():
            if k not in out:
                out[k] = r
            elif key == "p":
                ms.union_matches(out[k], r)
    ms.dump_atomic(os.path.join(ROOT, out_name), list(out.values()))
    print(f"{out_name}: {len(out)} records", flush=True)


if __name__ == "__main__":
    build("probe_log.jsonl", ["probe_log_b.jsonl", "probe_log_c.jsonl"],
          "p", "probe_log_all.jsonl")
    build("search_rows.jsonl", ["search_rows_b.jsonl", "search_rows_c.jsonl"],
          "id", "search_rows_all.jsonl")
