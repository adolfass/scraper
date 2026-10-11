#!/usr/bin/env python3
"""Harvest ANNEX article lists from FSA certificate print-forms.

Key facts discovered:
  * The registry has ~2.6M certificates; our article search only ever surfaced
    a tiny slice.
  * Search column `productIdentificationTrademark` lets us enumerate ALL
    certificates of a brand (including "annex-only" ones whose article list is
    NOT in the machine-readable card).
  * POST /api/v1/rss/common/certificates/{id}/export/docx returns the full
    print-form which CONTAINS the annex article list ("Артикул ...").

Subcommands:
  search   enumerate certs per price-list brand (trademark column)
  fetch    download print-form exports (+ detail cards where needed)
  match    extract article tokens from exports, match price codes

State:  /tmp/annex/certs_index.json, /tmp/annex/docx/<cid>.docx
"""
import io
import json
import os
import re
import sys
import time
import zipfile
from collections import defaultdict

import openpyxl

import fsa_api

WORK = os.environ.get("ANNEX_WORK", "/tmp/annex")
IDX = os.environ.get("ANNEX_IDX", f"{WORK}/certs_index.json")
DOCX = os.environ.get("ANNEX_DOCX", f"{WORK}/docx")
COL = os.environ.get("SEARCH_COL", "productIdentificationTrademark")
TOK = re.compile(r"[0-9a-zа-яё]+")
SRC = "/Users/mac/Downloads/Итоговый ИП.xlsx"
OUT = "Итоговый ИП_Результат.xlsx"


def load_brands():
    wb = openpyxl.load_workbook(OUT, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    it = ws.iter_rows(values_only=True)
    h = list(next(it))
    bi = h.index("BrandName")
    brands = {}
    for r in it:
        b = str(r[bi] or "").strip().lower()
        if b and b != "zekkert":
            brands[b] = brands.get(b, 0) + 1
    wb.close()
    return brands


def load_codes():
    """code -> brand (only rows still lacking a certificate)."""
    wb = openpyxl.load_workbook(OUT, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    it = ws.iter_rows(values_only=True)
    h = list(next(it))
    ci, bi, ni = h.index("Code"), h.index("BrandName"), h.index("CertNumber")
    un = {}
    for r in it:
        c = str(r[ci] or "").strip().lower()
        if c and not (r[ni] and str(r[ni]).strip()):
            un[c] = str(r[bi] or "").strip().lower()
    wb.close()
    return un


def _get(path, body, tries=3):
    last = None
    for i in range(tries):
        try:
            st, data = fsa_api._call("POST", path, body=body, retries=1)
            return st, data
        except Exception as e:
            last = e
            time.sleep(2.0 * (i + 1))
    return None, last


def search(brand, cap):
    ids = []
    page = 0
    while len(ids) < cap:
        body = {"size": 100, "page": page,
                "filter": {"idCertScheme": [],
                           "regDate": {"startDate": None, "endDate": None},
                           "endDate": {"startDate": None, "endDate": None},
                           "columnsSearch": [{"column": COL, "search": brand, "type": 0}]},
                "columnsSort": [{"column": "date", "sort": "DESC"}]}
        st, data = _get("/api/v1/rss/common/certificates/get", body)
        if st != 200 or not isinstance(data, dict):
            break
        items = data.get("items") or []
        for it in items:
            ids.append(it)
        if len(items) < 100:
            break
        page += 1
        time.sleep(0.5)
    return ids


def cmd_search():
    cap = int(os.environ.get("CAP", "200"))
    os.makedirs(WORK, exist_ok=True)
    brands = load_brands()
    names = sorted(brands)
    if len(sys.argv) > 2:
        names = sys.argv[2:]
    bf = os.environ.get("BRANDS_FILE")
    if bf and os.path.exists(bf):
        names = [l.strip() for l in open(bf, encoding="utf-8") if l.strip()]
    idx = {}
    if os.path.exists(IDX):
        idx = json.load(open(IDX, encoding="utf-8"))
    done = set(idx.get("__done__", []))
    certs = idx.get("certs", {})
    for n, b in enumerate(names, 1):
        if b in done:
            continue
        t0 = time.time()
        items = search(b, cap)
        for it in items:
            cid = str(it.get("id"))
            rec = certs.setdefault(cid, {"number": it.get("number"),
                                         "date": it.get("date"),
                                         "idStatus": it.get("idStatus"),
                                         "certType": it.get("certType"),
                                         "manufacterName": it.get("manufacterName"),
                                         "applicantName": it.get("applicantName"),
                                         "brands": []})
            if b not in rec["brands"]:
                rec["brands"].append(b)
        done.add(b)
        print(f"[{n}/{len(names)}] {b:18} items={len(items)} "
              f"total_certs={len(certs)} ({time.time()-t0:.0f}s)", flush=True)
        json.dump({"__done__": sorted(done), "certs": certs},
                  open(IDX, "w"), ensure_ascii=False)
        time.sleep(0.5)
    print(f"search done: {len(certs)} certs", flush=True)


def docx_text(data):
    z = zipfile.ZipFile(io.BytesIO(data))
    xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", xml))


def get_export(cid):
    path = f"{DOCX}/{cid}.docx"
    if os.path.exists(path) and os.path.getsize(path) > 200:
        return True
    st, data = _get(f"/api/v1/rss/common/certificates/{cid}/export/docx", {}, tries=3)
    if st == 200 and isinstance(data, (bytes, bytearray)) and data[:2] == b"PK":
        os.makedirs(DOCX, exist_ok=True)
        open(path, "wb").write(data)
        return True
    return False


def cmd_fetch():
    idx = json.load(open(IDX, encoding="utf-8"))
    cids = list(idx["certs"])
    nshard = int(os.environ.get("NSHARD", "1"))
    shard = int(os.environ.get("SHARD", "0"))
    if nshard > 1:
        cids = [c for c in cids if int(c) % nshard == shard]
    if not os.path.isdir(DOCX) and cids:
        os.makedirs(DOCX, exist_ok=True)
    ok = fail = 0
    t0 = time.time()
    for i, cid in enumerate(cids, 1):
        try:
            if get_export(cid):
                ok += 1
            else:
                fail += 1
        except Exception as e:
            fail += 1
            print(f"  {cid} err {str(e)[:60]}", flush=True)
        if i % 25 == 0:
            print(f"  [{i}/{len(cids)}] ok={ok} fail={fail} ({time.time()-t0:.0f}s)",
                  flush=True)
        time.sleep(0.3)
    print(f"fetch done ok={ok} fail={fail}", flush=True)


def search_col(col, q, cap):
    """Generic search by an arbitrary searchable column."""
    ids = []
    page = 0
    while len(ids) < cap:
        body = {"size": 100, "page": page,
                "filter": {"idCertScheme": [],
                           "regDate": {"startDate": None, "endDate": None},
                           "endDate": {"startDate": None, "endDate": None},
                           "columnsSearch": [{"column": col, "search": q, "type": 0}]},
                "columnsSort": [{"column": "date", "sort": "DESC"}]}
        st, data = _get("/api/v1/rss/common/certificates/get", body)
        if st != 200 or not isinstance(data, dict):
            break
        items = data.get("items") or []
        ids.extend(items)
        if len(items) < 100:
            break
        page += 1
        time.sleep(0.4)
    return ids


def _add_cert(certs, it):
    cid = str(it.get("id"))
    if cid in certs:
        return False
    certs[cid] = {"number": it.get("number"), "date": it.get("date"),
                  "idStatus": it.get("idStatus"), "certType": it.get("certType"),
                  "manufacterName": it.get("manufacterName"),
                  "applicantName": it.get("applicantName"), "brands": []}
    return True


def cmd_expand():
    """Find SIBLING certificates of the same holder (manufacturer/applicant).

    Exploits the grouping rule: one holder certifies one product family and the
    family's full article list lives in each certificate's annex.  A holder
    often splits the family across several certificates/blank ranges, so from a
    certificate that already matched we walk to all its siblings by searching
    `manufacterName` / `applicantName`.
    """
    idx = json.load(open(IDX, encoding="utf-8"))
    certs = idx.setdefault("certs", {})
    src_arg = sys.argv[2:]
    cap = int(os.environ.get("EXP_CAP", "300"))
    keys, seen = [], set()

    def add_key(col, q):
        q = (q or "").strip()
        if len(q) >= 6 and (col, q) not in seen:
            seen.add((col, q)); keys.append((col, q))

    if src_arg and os.path.isfile(src_arg[0]):
        lines = [l.rstrip("\n") for l in open(src_arg[0], encoding="utf-8") if l.strip()]
        if lines and "\t" in lines[0]:
            for l in lines:
                col, q = l.split("\t", 1)
                add_key(col, q)
            src = []
        else:
            src = lines
    elif src_arg:
        src = src_arg
    else:
        src = list(certs)
    if not keys:
        for cid in src:
            c = certs.get(str(cid)) or {}
            add_key("manufacterName", c.get("manufacterName"))
            add_key("applicantName", c.get("applicantName"))
    print(f"expand: src={len(src)} holder-keys={len(keys)} cap={cap}", flush=True)
    new_ids, errs = set(), 0
    for n, (col, q) in enumerate(keys, 1):
        try:
            items = search_col(col, q, cap)
        except Exception as e:
            errs += 1
            print(f"  [{n}/{len(keys)}] {col}={q[:40]!r} ERR {str(e)[:50]}", flush=True)
            continue
        add = sum(1 for it in items if _add_cert(certs, it))
        new_ids.update(cid for cid in (str(it.get("id")) for it in items) if cid)
        print(f"  [{n}/{len(keys)}] {col}={q[:36]!r} got={len(items)} new={add} total={len(certs)}", flush=True)
        json.dump({"__done__": idx.get("__done__", []), "certs": certs},
                  open(IDX, "w"), ensure_ascii=False)
        time.sleep(0.3)
    print(f"expand done: keys={len(keys)} errs={errs} total={len(certs)}", flush=True)


def cmd_match():
    import build_output as B
    un = load_codes()
    allc = {}
    wb = openpyxl.load_workbook(OUT, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    it = ws.iter_rows(values_only=True)
    h = list(next(it))
    ci, bi = h.index("Code"), h.index("BrandName")
    for r in it:
        c = str(r[ci] or "").strip().lower()
        if c:
            allc[c] = str(r[bi] or "").strip().lower()
    wb.close()
    codes = sorted(set(allc))
    sq = {c: re.sub(r"[^0-9a-zа-яё]", "", c) for c in codes}

    files = sorted(f for f in os.listdir(DOCX) if f.endswith(".docx"))
    print(f"exports={len(files)} codes={len(codes)} unmatched={len(un)}", flush=True)
    hits = defaultdict(list)   # code -> [(cid, brand_ok)]
    for n, f in enumerate(files, 1):
        cid = f[:-5]
        try:
            t = docx_text(open(f"{DOCX}/{f}", "rb").read())
        except Exception:
            continue
        toks = set(TOK.findall(t.lower()))
        flat = re.sub(r"[^0-9a-zа-яё]", "", t.lower())
        nb = B.norm_text(t)
        for c in codes:
            if c in toks or (len(sq[c]) >= 5 and sq[c] in flat):
                b = allc[c]
                brand_ok = B.brand_matches(b, nb) if b else False
                hits[c].append((cid, brand_ok))
        if n % 200 == 0:
            print(f"  scanned {n}/{len(files)} distinct_codes={len(hits)}", flush=True)
    json.dump({c: v for c, v in hits.items()}, open(f"{WORK}/hits.json", "w"),
              ensure_ascii=False)
    print(f"codes with any export match: {len(hits)}", flush=True)
    print(f"  of which unmatched: {sum(1 for c in hits if c in un)}", flush=True)
    print(f"  brand-gated pairs: {sum(1 for v in hits.values() for _, b in v if b)}",
          flush=True)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "match"
    {"search": cmd_search, "fetch": cmd_fetch, "expand": cmd_expand,
     "match": cmd_match}[cmd]()
