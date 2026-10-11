#!/usr/bin/env python3
"""Attach a BRAND-GROUP certificate to manufacturers whose certificate is not
listed verbatim in any harvested annex.

Same method that resolved the two examples:
  * LI AUTO   -> cert 3716140  (Beijing Lixiang Automobile)
  * BODYPARTS -> cert 3439963  (AWAK HANDEL / ФОРВАРД АВТО ПАРТС)

Both were found by querying the register's *product identification* columns
(productIdentificationName / productIdentificationTrademark) rather than the
article column.  This script runs that query for every brand that still has
empty certificate cells, verifies each candidate against the detail card
(brand token present in the product list / trademark / annex articles) and
attaches the best certificate to the brand's rows.

Env:
  BG_IN     input workbook      (default /tmp/Итоговый_ИП_brand2.xlsx)
  BG_OUT    output workbook     (default /tmp/Итоговый_ИП_group.xlsx)
  BG_ONLY   comma list of brands to restrict to (debug)
  BG_NLIVE  live search page cap per column (default 60)
  BG_NTOP   candidate detail cap per brand   (default 25)
  BG_CACHE  brand -> candidate-id cache
"""
import json
import os
import re
import time
from collections import defaultdict, Counter

import openpyxl

import fsa_api
import pipeline
import build_output as B

WORK = "/tmp/annex"
IDX = os.environ.get("ANNEX_IDX", f"{WORK}/certs_index.json")
TNVED_TREE = os.path.join(pipeline.ROOT, "tnved_tree.json")
IN_FILE = os.environ.get("BG_IN", "/tmp/Итоговый_ИП_brand2.xlsx")
OUT_FILE = os.environ.get("BG_OUT", "/tmp/Итоговый_ИП_group.xlsx")
CACHE = os.environ.get("BG_CACHE", f"{WORK}/brand_search.json")
NLIVE = int(os.environ.get("BG_NLIVE", "60"))
NTOP = int(os.environ.get("BG_NTOP", "25"))
ONLY = [b.strip().lower() for b in os.environ.get("BG_ONLY", "").split(",") if b.strip()]

COLS = ("productIdentificationName", "productIdentificationTrademark", "manufacterName")
ALNUM = re.compile(r"[^0-9a-zа-яё]")
ITEM_SPLIT = re.compile(r"[,;\s]+")
STOP = {"motors", "motor", "auto", "autos", "parts", "part", "group", "brand",
        "ltd", "inc", "spa", "gmbh", "corp", "the", "and", "co", "llc", "sa"}


def load_tnved():
    id2code = {}
    if os.path.exists(TNVED_TREE):
        tree = json.load(open(TNVED_TREE, encoding="utf-8"))
        id2code = {int(k): v.get("code") for k, v in tree.items()
                   if v.get("code") and str(v.get("code")).isdigit()}
    return id2code


def union_tnved(detail, id2code):
    idents = (detail.get("product") or {}).get("identifications") or []
    out = []
    for ident in idents:
        ids = ident.get("idTnveds") or []
        ids = [t.get("id") if isinstance(t, dict) else t for t in ids]
        for t in ids:
            if t in id2code:
                out.append(id2code[t])
    return ";".join(dict.fromkeys(out))


def search(col, q, cap):
    out = []
    page = 0
    while len(out) < cap:
        body = {"size": 100, "page": page,
                "filter": {"idCertScheme": [],
                           "regDate": {"startDate": None, "endDate": None},
                           "endDate": {"startDate": None, "endDate": None},
                           "columnsSearch": [{"column": col, "search": q, "type": 0}]},
                "columnsSort": [{"column": "date", "sort": "DESC"}]}
        st = data = None
        for attempt in range(3):
            try:
                st, data = fsa_api._call("POST", "/api/v1/rss/common/certificates/get",
                                         body=body, retries=1)
            except Exception:
                st, data = None, None
            if st == 200 and isinstance(data, dict):
                break
            time.sleep(2.0 * (attempt + 1))
        if st != 200 or not isinstance(data, dict):
            break
        items = data.get("items") or []
        out += items
        if len(items) < 100:
            break
        page += 1
        time.sleep(0.4)
    return out


def brand_keys(b):
    keys = [b]
    for p in re.split(r"[/,&]+", b):
        p = p.strip()
        if p and p != b:
            keys.append(p)
    # spelling variants (multi-word / hyphenated / punctuation brands)
    variants = set()
    for k in list(keys):
        variants.add(re.sub(r"[^0-9a-zа-яё]", "", k))
        for w in re.split(r"[\s\-\u2013]+", k):
            if len(w) >= 4 and w not in STOP:
                variants.add(w)
    for v in variants:
        if v and v not in keys:
            keys.append(v)
    return keys


def brand_rx(b):
    return re.compile(r"(?<![0-9a-z])" + re.escape(b) + r"(?![0-9a-z])")


def load_rows():
    wb = openpyxl.load_workbook(IN_FILE, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    it = ws.iter_rows(values_only=True)
    header = list(next(it))
    ci, bi, ni = header.index("Code"), header.index("BrandName"), header.index("CertNumber")
    rows = []
    empty = defaultdict(list)          # brand -> [row index]
    codes = defaultdict(set)           # brand -> {normalised code}
    for r in it:
        row = list(r)
        rows.append(row)
        b = str(row[bi] or "").strip().lower()
        if not b or b == "zekkert":
            continue
        if not (row[ni] and str(row[ni]).strip()):
            empty[b].append(len(rows) - 1)
            c = str(row[ci] or "").strip().lower()
            if c:
                codes[b].add(ALNUM.sub("", c))
    wb.close()
    return header, rows, empty, codes


def main():
    header, rows, empty, codes = load_rows()
    print(f"input rows={len(rows)} empty brands={len(empty)} "
          f"empty rows={sum(len(v) for v in empty.values())}", flush=True)

    idx = {}
    if os.path.exists(IDX):
        idx = json.load(open(IDX, encoding="utf-8")).get("certs", {})
    index_by_brand = defaultdict(list)
    meta = {}
    for cid, rec in idx.items():
        for b in rec.get("brands", []):
            index_by_brand[b].append(cid)
        meta[cid] = {"number": rec.get("number"), "date": rec.get("date"),
                     "idStatus": rec.get("idStatus"), "certType": rec.get("certType"),
                     "manufacterName": rec.get("manufacterName"),
                     "applicantName": rec.get("applicantName")}

    brands = sorted(empty)
    if ONLY:
        brands = [b for b in brands if b in ONLY]
    cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}

    # ---- candidate discovery (cached) ----
    for i, b in enumerate(brands, 1):
        if b in cache:
            continue
        s = set(index_by_brand.get(b, []))
        for key in brand_keys(b):
            for col in COLS:
                try:
                    items = search(col, key, NLIVE)
                except Exception as e:
                    print(f"   search {col}={key!r} err {str(e)[:50]}", flush=True)
                    items = []
                for it2 in items:
                    cid = str(it2.get("id"))
                    s.add(cid)
                    meta.setdefault(cid, {"number": it2.get("number"), "date": it2.get("date"),
                                          "idStatus": it2.get("idStatus"),
                                          "certType": it2.get("certType"),
                                          "manufacterName": it2.get("manufacterName"),
                                          "applicantName": it2.get("applicantName")})
                time.sleep(0.3)
        cache[b] = sorted(s)
        json.dump(cache, open(CACHE, "w"), ensure_ascii=False)
        print(f"[{i}/{len(brands)}] {b}: cands={len(cache[b])}", flush=True)

    # ---- pick candidates to inspect ----
    def cand_sort(cid):
        m = meta.get(cid, {})
        return (1 if m.get("idStatus") == 6 else 0, str(m.get("date") or ""))

    pool = {}
    need = set()
    for b in brands:
        cs = sorted(cache.get(b, []), key=cand_sort, reverse=True)[:NTOP]
        pool[b] = cs
        need.update(cs)

    cards = {k: v["data"] for k, v in
             pipeline.load_jsonl(pipeline.CERTS_LOG, key="id").items()
             if v.get("data") is not None}
    missing = sorted(need - set(cards), key=lambda x: int(x))
    print(f"details needed={len(need)} missing={len(missing)}", flush=True)
    _todo = [] if os.environ.get("BG_NOFETCH") == "1" else missing
    for j, cid in enumerate(_todo, 1):
        try:
            data = pipeline.get_cert(cid)
        except Exception:
            continue
        if not data:
            continue
        cards[cid] = data
        pipeline._append(pipeline.CERTS_LOG, {"id": cid, "data": data})
        if j % 25 == 0:
            print(f"   details {j}/{len(missing)}", flush=True)
    print("detail fetch done", flush=True)

    # ---- choose + attach ----
    id2code = load_tnved()
    attach = {}
    audit = []
    for b in brands:
        rxs = [brand_rx(k) for k in brand_keys(b)]
        bcodes = codes.get(b, set())
        best, bestkey = None, None
        for cid in pool.get(b, []):
            d = cards.get(cid)
            if d is None:
                # unverified candidate: keep only as last resort
                m = meta.get(cid, {})
                key = (0, 0, 0, 1 if m.get("idStatus") == 6 else 0,
                       str(m.get("date") or ""))
                if best is None or key > bestkey:
                    best, bestkey = cid, key
                continue
            prod = d.get("product") or {}
            idents = prod.get("identifications") or []
            man = (d.get("manufacturer") or {}).get("fullName") or ""
            app = (d.get("applicant") or {}).get("fullName") or ""
            extra = B.norm_text(" ".join([str(prod.get("fullName") or ""), str(man), str(app)]))
            ntxt = (" ".join(B.norm_text(str(x.get("name") or "")) for x in idents)
                    + " " + extra).lower()
            ttxt = " ".join(B.norm_text(str(x.get("tradeMark") or "")) for x in idents).lower()
            atxt = " ".join(str(x.get("article") or "") for x in idents).lower()
            name_hit = any(r.search(ntxt) for r in rxs)
            tm_hit = any(r.search(ttxt) for r in rxs)
            items = {ALNUM.sub("", w) for w in ITEM_SPLIT.split(atxt) if w}
            art_hit = sum(1 for k in bcodes if len(k) >= 5 and k in items)
            m = meta.get(cid, {})
            key = (1 if art_hit else 0, 1 if name_hit else 0, 1 if tm_hit else 0,
                   1 if m.get("idStatus") == 6 else 0, str(m.get("date") or ""))
            if best is None or key > bestkey:
                best, bestkey = cid, key
        if best is None or not (bestkey[0] or bestkey[1] or bestkey[2]):
            print(f"   {b}: no verified cert (cands={len(pool.get(b,[]))})", flush=True)
            continue
        cid = best
        m = idx.get(cid) or meta.get(cid) or {}
        detail = cards.get(cid)
        number = m.get("number") or (detail or {}).get("number") or ""
        ctype = B.cert_type_of(m) if m else None
        if ctype is None and detail:
            ctype = B.cert_type_of(detail)
        url = B.CERT_URL.format(id=cid)
        tnved = B.cap_tnved(union_tnved(detail, id2code)) if detail else ""
        for ridx in empty[b]:
            attach[ridx] = (number, url, tnved, ctype or "Сертификат", cid)
        audit.append([b, cid, number, bestkey[0], bestkey[1], bestkey[2], len(empty[b])])
        print(f"   {b:16} <- {cid} art={bestkey[0]} name={bestkey[1]} tm={bestkey[2]} "
              f"rows={len(empty[b])} {number[:34]}", flush=True)

    # ---- write ----
    ci, ni = header.index("CertNumber"), header.index("CertNumber")
    ui, ti, yi = header.index("CertUrl"), header.index("TNVED"), header.index("CertType")
    st = Counter()
    for ridx, (number, url, tnved, ctype, cid) in attach.items():
        rows[ridx][ni] = number
        rows[ridx][ui] = url
        rows[ridx][ti] = tnved
        rows[ridx][yi] = ctype
        st["filled"] += 1
        if tnved:
            st["with_tnved"] += 1
    owb = openpyxl.Workbook(write_only=True)
    ows = owb.create_sheet("PRICE")
    ows.append(header)
    for r in rows:
        r = ["" if v is None else v for v in r]
        if len(r) < len(header):
            r += [""] * (len(header) - len(r))
        ows.append(r)
    owb.save(OUT_FILE)
    json.dump(audit, open(f"{WORK}/brand_group_audit.json", "w"), ensure_ascii=False, indent=1)
    print(f"brand-group brands={len(audit)} stats={dict(st)}", flush=True)
    print(f"written {OUT_FILE} ({len(rows)} rows)", flush=True)


if __name__ == "__main__":
    main()
