#!/usr/bin/env python3
"""Carry ref's rds/declaration links into decl_certs.json (same shape as
other_certs.json) after verifying each of the ~62 unique declaration ids
against the live card API:

  GET /api/v1/rds/common/declarations/{id}  ->  {number, ...}

Number comes from the LIVE card when the fetch succeeds (ref only as
fallback); verified=True only on successful fetch + number agreement.
"""
import json, os, re, sys, time
import openpyxl

import fsa_api
from other_sources import norm_num

ROOT = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(ROOT, "Готовый.xlsx")
OUT = os.path.join(ROOT, "decl_certs.json")
DELAY = float(os.environ.get("DELAY", "1.0"))


def load_ref_decls():
    wb = openpyxl.load_workbook(REF, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    it = ws.iter_rows(values_only=True)
    hdr = list(next(it))
    idx = {h: i for i, h in enumerate(hdr)}
    out = {}
    ids = {}
    for r in it:
        url = str(r[idx["CertUrl"]] or "")
        m = re.search(r"/rds/declaration/view/([0-9a-zA-Z-]+)", url)
        if not m:
            continue
        did = m.group(1)
        key = f"{str(r[idx['ProdNum']] or '').strip()}|{str(r[idx['Code']] or '').strip().lower()}"
        rec = {"number": str(r[idx["CertNumber"]] or "").strip(),
               "url": url,
               "tnved": str(r[idx["TNVED"]] or "").strip(),
               "type": str(r[idx["CertType"]] or "").strip() or "Декларация"}
        out[key] = rec
        ids.setdefault(did, []).append(key)
    wb.close()
    return out, ids


def main():
    entries, ids = load_ref_decls()
    print(f"ref decl rows: {len(entries)}, unique ids: {len(ids)}", flush=True)

    # cache previous runs
    cache = {}
    if os.path.exists(OUT):
        # id cache lives next to entries; refetch anyway (cheap, 62 ids)
        pass

    live = {}
    failed = []
    for i, did in enumerate(sorted(ids), 1):
        try:
            st, data = fsa_api._call("GET", f"/api/v1/rds/common/declarations/{did}")
        except Exception as e:
            st, data = 0, str(e)
        if st == 200 and isinstance(data, dict):
            live[did] = data
        else:
            failed.append((did, st, str(data)[:80]))
        if i % 10 == 0:
            print(f"  fetched {i}/{len(ids)}", flush=True)
        time.sleep(DELAY)
    print(f"live cards: {len(live)}, failed: {len(failed)}", flush=True)
    for f in failed:
        print("  FAIL", f, flush=True)

    if live:
        sample = next(iter(live.values()))
        print("card keys:", sorted(sample.keys()), flush=True)

    n_ver = n_mismatch = n_nofetch = 0
    mismatches = []
    for did, keys in ids.items():
        card = live.get(did)
        ref_num = entries[keys[0]]["number"]
        if card is None:
            n_nofetch += 1
            continue
        card_num = str(card.get("number") or card.get("declNumber") or "").strip()
        if not card_num:
            n_nofetch += 1
            continue
        ok = norm_num(card_num) == norm_num(ref_num)
        if ok:
            n_ver += 1
        else:
            n_mismatch += 1
            mismatches.append((did, ref_num, card_num))
        for k in keys:
            entries[k]["number"] = card_num      # live number is the truth
            entries[k]["verified"] = bool(ok)
            entries[k]["host"] = "rds"
            if not ok:
                entries[k]["ref_number"] = ref_num
    for did, keys in ids.items():
        if not entries[keys[0]].get("host"):
            for k in keys:
                entries[k]["verified"] = False
                entries[k]["host"] = "rds"

    print(f"verified: {n_ver}, number mismatch: {n_mismatch}, "
          f"no live card: {n_nofetch}", flush=True)
    for m in mismatches[:20]:
        print("  MISMATCH", m, flush=True)

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=1)
    print(f"written {OUT}: {len(entries)} entries", flush=True)


if __name__ == "__main__":
    main()
