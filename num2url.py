#!/usr/bin/env python3
"""Fill CertUrl for ref rows that have a CertNumber but no CertUrl.

For each unique ref number:
  1. clean it (NBSP->space, collapse ws, strip trailing range like ' 1-30');
  2. build query fragments: cleaned full, last token, last token minus /YY,
     the 'XX99.B.99999' core - each in identity / Latin->Cyrillic /
     Cyrillic->Latin homoglyph folds (deduped, <=8 queries per number);
  3. search FSA:
       CertType 'Декларац*' -> POST /api/v1/rds/common/declarations/get
         filter.columnsSearch [{name:"number", search, type:0}]
       otherwise            -> POST /api/v1/rss/common/certificates/get
         filter.columnsSearch [{column:"number", search}]   (size=100, sort DESC)
     pick hits whose normalized number equals the cleaned ref number
     (prefer idStatus=6), build the card URL;
  4. last resort: digits core (>=4 digits) paged up to 3x100.

Misses (e.g. KG/KZ national numbers absent from FSA and eaeunion - probed by
docId equality and literal-prefix regex on tech.eaeunion.org spd/find) are
emitted as number-only entries (url="", verified=False) so the row still gets
the ref number; build_output prefers any real FSA cert for the same key.

Emits num2url_certs.json (same shape as other_certs.json, keyed "ProdNum|Code").

Run gentle: DELAY seconds between requests (default 1.0).
"""
import json, os, re, sys, time
from collections import defaultdict
import openpyxl

import fsa_api
from other_sources import norm_num

ROOT = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(ROOT, "Готовый.xlsx")
OUT = os.path.join(ROOT, "num2url_certs.json")
DELAY = float(os.environ.get("DELAY", "1.0"))
RSS_URL = "https://pub.fsa.gov.ru/rss/certificate/view/{id}/product"
RDS_URL = "https://pub.fsa.gov.ru/rds/declaration/view/{id}/common"

# homoglyph folds (visually identical letter pairs)
_LAT = "ABCEHKMOPTXabcehkmoptx"
_CYR = "АВСЕНКМОРТХавсенкмоптх"
L2C = str.maketrans(_LAT, _CYR)
C2L = str.maketrans(_CYR, _LAT)


def clean_number(num):
    s = str(num).replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return re.sub(r"\s+\d+-\d+$", "", s)          # trailing range ' 1-30'


def queries(number):
    """Distinctive search queries for a (cleaned) number, best first."""
    out = []

    def add(s):
        if s and len(s) >= 4 and s not in out:
            out.append(s)

    add(number)
    toks = number.split()
    if toks:
        last = toks[-1]
        add(last)
        add(re.sub(r"[/.\s]\d{2,4}$", "", last))   # drop trailing /24 or .23
    m = re.search(r"[А-ЯA-Za-z]{1,3}\d{1,3}\.[А-ЯA-Za-z]\.\d{4,5}", number)
    if m:
        add(m.group(0))                            # e.g. НА90.В.00617
    base = list(out)
    for s in base:                                 # homoglyph folds
        add(s.translate(L2C))
        add(s.translate(C2L))
    return out


def digits_core(number):
    m = re.findall(r"\d{4,}", number)
    return m[-1] if m else None


def search(q, is_decl):
    body = {"size": 100, "page": 0,
            "filter": {"columnsSearch": (
                [{"name": "number", "search": q, "type": 0}] if is_decl
                else [{"column": "number", "search": q}])},
            "columnsSort": [{"column": "id", "sort": "DESC"}]}
    path = ("/api/v1/rds/common/declarations/get" if is_decl
            else "/api/v1/rss/common/certificates/get")
    st, res = fsa_api._call("POST", path, body)
    if not isinstance(res, dict):
        return None, f"http {st}"
    return (res.get("items") or []), None


def find_cert(number, is_decl, log):
    """-> (best_item | None, err | None)"""
    tnum = norm_num(number)
    queries_ = queries(number)
    for qi, q in enumerate(queries_, 1):
        items, err = search(q, is_decl)
        if items is None:
            log.append(f"q{qi} {q!r}: {err}")
            return None, err
        exact = [x for x in items
                 if norm_num(str(x.get("number") or "")) == tnum]
        log.append(f"q{qi} {q!r}: {len(items)} hits, {len(exact)} exact")
        if exact:
            return max(exact, key=lambda x: (x.get("idStatus") == 6,
                                             str(x.get("date") or ""))), None
        time.sleep(DELAY)
    core = digits_core(number)
    if core:
        for page in range(3):                      # last resort: digits pages
            items, err = search(core, is_decl)
            if items is None:
                return None, err
            exact = [x for x in items
                     if norm_num(str(x.get("number") or "")) == tnum]
            log.append(f"core {core!r} p{page}: {len(items)} hits, "
                       f"{len(exact)} exact")
            if exact:
                return max(exact, key=lambda x: (x.get("idStatus") == 6,
                                                 str(x.get("date") or ""))), None
            time.sleep(DELAY)
    return None, None                              # genuine miss


def load_ref_numberless():
    wb = openpyxl.load_workbook(REF, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    it = ws.iter_rows(values_only=True)
    hdr = list(next(it))
    idx = {h: i for i, h in enumerate(hdr)}
    rows = []
    for r in it:
        num = str(r[idx["CertNumber"]] or "").strip()
        url = str(r[idx["CertUrl"]] or "").strip()
        if not num or url:
            continue
        rows.append({
            "key": f"{str(r[idx['ProdNum']] or '').strip()}|"
                   f"{str(r[idx['Code']] or '').strip().lower()}",
            "number": num,
            "tnved": str(r[idx["TNVED"]] or "").strip(),
            "type": str(r[idx["CertType"]] or "").strip(),
        })
    wb.close()
    return rows


def main():
    rows = load_ref_numberless()
    by_num = defaultdict(list)
    for r in rows:
        by_num[r["number"]].append(r)
    print(f"ref rows with number & no url: {len(rows)}, "
          f"unique numbers: {len(by_num)}", flush=True)

    entries = {}
    stats = {"found": 0, "miss": 0, "error": 0}
    rows_found = rows_miss = 0
    for i, (raw_num, keys) in enumerate(sorted(by_num.items()), 1):
        number = clean_number(raw_num)
        is_decl = ("Декларац" in keys[0]["type"]
                   or " RU Д-" in number or " RU Д" in number)
        log = []
        try:
            best, err = find_cert(number, is_decl, log)
        except Exception as e:
            best, err, log = None, str(e)[:80], log + [f"EXC {e}"]
        if err:
            stats["error"] += 1
            print(f"  [{i}] {number}: ERROR {err}", flush=True)
        elif best is not None:
            stats["found"] += 1
            rows_found += len(keys)
            cid = best.get("id")
            url = (RDS_URL if is_decl else RSS_URL).format(id=cid)
            if is_decl:
                ctype = keys[0]["type"] or "Декларация"
            else:
                ct = (best.get("certType") or "").lower()
                ctype = ("Декларация" if "декларац" in ct else
                         "Сертификат" if "сертификат" in ct else
                         "Декларация" if re.search(r"Д-| RU Д",
                                                   str(best.get("number") or ""))
                         else "Сертификат")
            for r in keys:
                entries[r["key"]] = {
                    "number": str(best.get("number") or number),  # live truth
                    "url": url, "tnved": r["tnved"],
                    "type": ctype, "verified": True,
                    "host": "rds_num" if is_decl else "fsa_num"}
            print(f"  [{i}] {number}: FOUND id={cid} "
                  f"({len(keys)} rows)", flush=True)
        else:
            stats["miss"] += 1
            rows_miss += len(keys)
            for r in keys:                          # number-only carry-over
                entries[r["key"]] = {
                    "number": r["number"], "url": "", "tnved": r["tnved"],
                    "type": r["type"], "verified": False, "host": "num_only"}
            print(f"  [{i}] {number}: miss, carry number only "
                  f"({len(keys)} rows) | {' | '.join(log[:4])}", flush=True)
        time.sleep(DELAY)

    print(f"done: {stats} | rows found={rows_found} miss={rows_miss}",
          flush=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=1)
    print(f"written {OUT}: {len(entries)} entries", flush=True)


if __name__ == "__main__":
    main()
