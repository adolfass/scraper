#!/usr/bin/env python3
"""Fetch reference documents of tech.eaeunion.org (96 unique certs) via OData.

For every non-FSA CertUrl in Готовый.xlsx ending in conformityDocs/view/{id}
we fetch the full document (articles in productDetails[].productName,
TNVED in commodityCode, status, dates).

Gentle (sequential, 0.8s pause, backoff) + resumable -> eae_docs.jsonl
({id, data|null, note}).
"""
import json, os, re, time, urllib.parse, urllib.request

import openpyxl

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "eae_docs.jsonl")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 Chrome/124.0",
      "Accept": "application/json"}
DELAY = 0.8


def ref_urls():
    wb = openpyxl.load_workbook(os.path.join(ROOT, "Готовый.xlsx"),
                                read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    it = ws.iter_rows(values_only=True)
    h = list(next(it))
    idx = {x: i for i, x in enumerate(h)}
    out = {}
    for r in it:
        url = str(r[idx["CertUrl"]] or "").strip()
        cert = str(r[idx["CertNumber"]] or "").strip()
        code = str(r[idx["Code"]] or "").strip().lower()
        if "tech.eaeunion.org" in url and "conformityDocs/view/" in url:
            oid = url.rsplit("/", 1)[-1]
            out.setdefault(oid, {"number": cert, "url": url, "codes": []})
            if code:
                out[oid]["codes"].append(code)
    wb.close()
    return out


def have():
    out = set()
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            for line in f:
                try:
                    out.add(json.loads(line)["id"])
                except Exception:
                    pass
    return out


def fetch(oid, timeout=40):
    q = ("$filter=" +
         urllib.parse.quote(f"Id eq '{oid}'", safe=""))
    req = urllib.request.Request(
        "https://tech.eaeunion.org/odata/conformityDocDetailsType?" + q,
        headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read())
    vals = data.get("value") or []
    return vals[0] if vals else None


def main():
    docs = ref_urls()
    done = have()
    todo = [(k, v) for k, v in sorted(docs.items()) if k not in done]
    print(f"ref eaeunion docs: {len(docs)}, cached: {len(done)}, "
          f"todo: {len(todo)}", flush=True)

    for n, (oid, meta) in enumerate(todo, 1):
        rec = {"id": oid, "number": meta["number"], "url": meta["url"]}
        for attempt in range(4):
            try:
                data = fetch(oid)
                if data is None:
                    rec["note"] = "not found"
                else:
                    rec["data"] = data
                break
            except Exception as e:
                wait = min(5 * 2 ** attempt, 120)
                print(f"  {oid} attempt {attempt + 1} failed: {e}; "
                      f"sleep {wait}s", flush=True)
                time.sleep(wait)
        else:
            rec["note"] = "gave up"
        with open(OUT, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        time.sleep(DELAY)
        if n % 10 == 0:
            print(f"  {n}/{len(todo)}", flush=True)
    print("done", flush=True)


if __name__ == "__main__":
    main()
