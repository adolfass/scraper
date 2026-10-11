#!/usr/bin/env python3
"""Restore TNVED on ref_carry entries from the DISPLAYED cert's own card. (v2)

Phase 4 switched ~74k rows from our FSA-chosen cert to ref's verified link,
but ref's TNVED column is mostly empty, so matched TNVED fell 169k -> 116k.
v1 restored 61,630 entries but 16,597 of them got a noisy card-scope UNION
(40..279 codes).  v2 applies a precision chain instead, always reading
TNVED from registry cards (correct attribution):

  for source in (Y = displayed cert, X = our FSA chosen cert,
                 C = every other candidate cert of this code):
      exact code -> ident_for_code semantics (token, then substring);
      variant    -> strip trailing revision letters ("028103534a" ->
                    "028103534"), TOKEN-EXACT match only (no substrings);
  else -> union of the displayed card's idents' idTnveds, CAPPED at 10.

Work is idempotent: always rebuilt from ref_carry_certs.json.bak (the
pre-TNVED state written by ref_carry.py).  All inputs are local - no HTTP.
Gentle by construction.
"""
import json
import os
import re
import shutil
import time
from collections import Counter

import build_output as bo

ROOT = os.path.dirname(os.path.abspath(__file__))
RC = os.path.join(ROOT, "ref_carry_certs.json")
BAK = RC + ".bak"
DECL_CACHE = os.path.join(ROOT, "ref_carry_decl_details.json")
UNION_CAP = 10
t0 = time.time()


def tick(msg):
    print(f"[{time.time() - t0:6.1f}s] {msg}", flush=True)


def load_cert_details():
    data = {}
    with open(os.path.join(ROOT, "certs.jsonl"), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("data") is not None:
                data[rec["id"]] = rec["data"]
    return data


def detail_index(d, cache):
    """-> (token->ident, [(art_lower, ident)]) built once per card."""
    key = id(d)
    if key in cache:
        return cache[key]
    tok, arts = {}, []
    idents = (d.get("product") or {}).get("identifications") or []
    for ident in idents:
        art = (ident.get("article") or "").lower()
        if not art:
            continue
        arts.append((art, ident))
        for t in bo.pipeline.TOKEN_SPLIT.split(art):
            if t and t not in tok:
                tok[t] = ident
    cache[key] = (tok, arts)
    return cache[key]


def find_ident(d, code, idx, allow_substr=True):
    tok, arts = detail_index(d, idx)
    ident = tok.get(code)
    if ident is not None:
        return ident
    if allow_substr:
        for art, ident in arts:
            if code in art:
                return ident
    return None


VARIANT_RE = re.compile(r"[a-zа-яё]+$")


def variants(code):
    """Revision-suffix form(s), token-exact only. No-op for bare codes."""
    out = []
    base = VARIANT_RE.sub("", code)
    if base and base != code and len(base) >= 5:
        out.append(base)
    return out


def id_tnveds(ident):
    ids = ident.get("idTnveds") or []
    return [t.get("id") if isinstance(t, dict) else t for t in ids]


def codes_of(ident, id2code):
    return list(dict.fromkeys(id2code[t] for t in id_tnveds(ident)
                              if t in id2code))


def main():
    if not os.path.exists(BAK):
        shutil.copy2(RC, BAK)
    rc = json.load(open(BAK, encoding="utf-8"))
    tick(f"entries from pre-TNVED state: {len(rc)}")

    certs = load_cert_details()
    decls = json.load(open(DECL_CACHE, encoding="utf-8"))
    tick(f"cert details: {len(certs)}, decl cards: {len(decls)}")

    tree = json.load(open(os.path.join(ROOT, "tnved_tree.json"),
                          encoding="utf-8"))
    id2code = {int(k): v.get("code") for k, v in tree.items()
               if v.get("code") and str(v.get("code")).isdigit()}
    tick(f"tnved dictionary: {len(id2code)}")

    log, rows, _ = bo.load_state()
    cand = bo.build_candidates(log)
    chosen = {c: bo.choose(rids, rows) for c, rids in cand.items()}
    tick(f"candidates: {len(cand)} codes, chosen: {len(chosen)}")

    def sort_rids(rids):
        return sorted(
            rids,
            key=lambda r: (1 if rows.get(r, {}).get("idStatus") == 6 else 0,
                           str(rows.get(r, {}).get("date") or "")),
            reverse=True)

    idx = {}
    st = Counter()

    def y_detail(v):
        u = v.get("url") or ""
        m = re.search(r"/view/([^/]+)", u)
        if not m:
            return None, u
        xid = m.group(1)
        if "/rds/" in u:
            return decls.get(xid), u
        return (certs.get(int(xid)) if xid.lstrip("-").isdigit()
                else None), u

    for k, v in rc.items():
        if v.get("tnved"):
            st["ref_tnved_kept"] += 1
            v["tnved_src"] = "ref"
            continue
        code = k.split("|", 1)[1] if "|" in k else ""
        if not code:
            st["no_code"] += 1
            continue
        yd, url = y_detail(v)
        xc = chosen.get(code)
        xd = certs.get(xc) if xc is not None else None
        sources = [("y", yd)]
        if xd is not None and xd is not yd:
            sources.append(("x", xd))
        other = [r for r in sort_rids(cand.get(code, ()))
                 if r != xc]
        found = None
        for src, d in sources:
            if d is None:
                continue
            for var, allow_sub in ((code, True),
                                   *[(vv, False) for vv in variants(code)]):
                ident = find_ident(d, var, idx, allow_sub)
                if ident:
                    codes_t = codes_of(ident, id2code)
                    if codes_t:
                        found = (src, codes_t)
                        break
            if found:
                break
        if not found and other:
            for rid in other:
                d = certs.get(rid)
                if d is None:
                    continue
                for var, allow_sub in ((code, True),
                                       *[(vv, False)
                                         for vv in variants(code)]):
                    ident = find_ident(d, var, idx, allow_sub)
                    if ident:
                        codes_t = codes_of(ident, id2code)
                        if codes_t:
                            found = ("cand", codes_t)
                            break
                if found:
                    break
        if found:
            src, codes_t = found
            v["tnved"] = ";".join(codes_t)
            v["tnved_src"] = src
            st[f"filled_{src}"] += 1
            continue
        # last resort: the displayed card's declared TNVED scope, capped.
        # NOTE: iterate ALL idents (incl. article-less ones - v1 parity).
        if yd is not None:
            idents = (yd.get("product") or {}).get("identifications") or []
            all_ids = [t for ident in idents for t in id_tnveds(ident)]
            codes_t = list(dict.fromkeys(id2code[t] for t in all_ids
                                         if t in id2code))[:UNION_CAP]
            if codes_t:
                v["tnved"] = ";".join(codes_t)
                v["tnved_src"] = "union"
                st["filled_union_capped"] += 1
                continue
        st["still_empty"] += 1

    json.dump(rc, open(RC, "w", encoding="utf-8"), ensure_ascii=False,
              indent=1)
    tick(f"stats: {dict(st)}")
    tick(f"written {RC}")


if __name__ == "__main__":
    main()
