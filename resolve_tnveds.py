#!/usr/bin/env python3
"""Resolve missing TNVED ids via the registry's batch endpoint.

Scans cert details (certs.jsonl) for identifications' idTnveds that are not
in tnved_tree.json, then resolves them in batches of 400 with

    POST https://pub.fsa.gov.ru/nsi/api/multi
    {"items": {"tnved": [{"id": [...], "fields": ["id","code","name"]}]}}

and merges the results into tnved_tree.json.  Run AFTER `pipeline.py details`.
"""
import json
import os
import time
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
CERTS = os.path.join(ROOT, "certs.jsonl")
TREE = os.path.join(ROOT, "tnved_tree.json")
URL = "https://pub.fsa.gov.ru/nsi/api/multi"
BATCH = 400
DELAY = 0.8


def missing_ids():
    tree = json.load(open(TREE, encoding="utf-8"))
    have = set(tree)
    need = set()
    n_details = 0
    with open(CERTS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            data = rec.get("data")
            if not data:
                continue
            n_details += 1
            idents = ((data.get("product") or {}).get("identifications") or [])
            for ident in idents:
                for t in ident.get("idTnveds") or []:
                    tid = t.get("id") if isinstance(t, dict) else t
                    if tid is not None and str(tid) not in have:
                        need.add(int(tid))
    return tree, sorted(need), n_details


def extract(obj):
    """Yield (id, code, name) triples from whatever shape multi returned."""
    if isinstance(obj, dict):
        if "id" in obj and ("code" in obj or "name" in obj):
            yield obj.get("id"), obj.get("code"), obj.get("name")
        else:
            for v in obj.values():
                yield from extract(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from extract(v)


def main():
    tree, need, n_details = missing_ids()
    print(f"details scanned: {n_details}, tree: {len(tree)}, "
          f"missing tnved ids: {len(need)}", flush=True)
    if not need:
        print("nothing to resolve", flush=True)
        return
    added = 0
    for i in range(0, len(need), BATCH):
        batch = need[i:i + BATCH]
        body = json.dumps({"items": {"tnved": [
            {"id": batch, "fields": ["id", "code", "name"]}]}})
        req = urllib.request.Request(
            URL, data=body.encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Accept": "application/json",
                     "User-Agent": "Mozilla/5.0"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                res = json.loads(r.read())
        except Exception as e:
            print(f"  batch {i // BATCH}: failed {e}", flush=True)
            time.sleep(5)
            continue
        got = 0
        for tid, code, name in extract(res):
            if tid is None:
                continue
            tree[str(tid)] = {"code": code, "name": name, "leaf": False}
            got += 1
        added += got
        print(f"  batch {i // BATCH}: asked {len(batch)}, got {got}", flush=True)
        time.sleep(DELAY)
    json.dump(tree, open(TREE, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"resolved {added}, tree now {len(tree)} -> {TREE}", flush=True)


if __name__ == "__main__":
    main()
