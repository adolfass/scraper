#!/usr/bin/env python3
"""Offline sweep: do UNMATCHED price-list codes appear anywhere in the already
downloaded certificate cards (any field), not just in the fields the matcher
reads (article / name / trademark)?

Also counts separator-bearing codes and how often cards are "annex-only"
(article = "согласно приложению"), where the real article list is not machine
readable and only the TU / standard remains.
"""
import json
import re
from collections import Counter

import openpyxl

TOKEN_RE = re.compile(r"[0-9a-zа-яё]+")
TU_RE = re.compile(r"\bТУ\s*[\d][\d.\-/–—]*", re.I)
ANNEX_RE = re.compile(r"согласно приложени", re.I)


def norm_tokens(s):
    return set(TOKEN_RE.findall(s.lower()))


def squash(s):
    return re.sub(r"[^0-9a-zа-яё]", "", s.lower())


def all_strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from all_strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from all_strings(v)


def unread_text(d):
    """Fields the matcher does NOT read: identification descriptions, TU
    document names, standards designations/names."""
    parts = []
    for idt in ((d.get("product") or {}).get("identifications") or []):
        if idt.get("description"):
            parts.append(str(idt["description"]))
        for doc in idt.get("documents") or []:
            if isinstance(doc, dict) and doc.get("name"):
                parts.append(str(doc["name"]))
        for st in idt.get("standards") or []:
            if isinstance(st, dict):
                parts.append(str(st.get("designation") or ""))
                parts.append(str(st.get("name") or ""))
    return " ".join(parts)


def main():
    # 1) unmatched codes from the shipped exact build
    unmatched = set()
    allcodes = set()
    wb = openpyxl.load_workbook("Итоговый ИП_Результат.xlsx",
                                read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    it = ws.iter_rows(values_only=True)
    h = list(next(it))
    ci, ni, bi = h.index("Code"), h.index("CertNumber"), h.index("BrandName")
    ubrand = {}
    for r in it:
        code = str(r[ci] or "").strip().lower()
        if not code:
            continue
        allcodes.add(code)
        if not (r[ni] and str(r[ni]).strip()):
            unmatched.add(code)
            ubrand.setdefault(code, str(r[bi] or "").strip().lower())
    wb.close()
    sep = {c for c in allcodes if re.search(r"[^0-9a-zа-яё]", c)}
    usep = {c for c in unmatched if re.search(r"[^0-9a-zа-яё]", c)}
    print(f"distinct codes={len(allcodes)} unmatched={len(unmatched)} "
          f"with separators={len(sep)} (unmatched {len(usep)})")

    # 2) stream cards, look for unmatched codes as exact normalized tokens
    found = Counter()          # code -> how many cards contain it as token (any field)
    found_unread_tok = Counter()
    found_squash = Counter()   # code -> cards containing squashed form (unread)
    long_un = {c for c in unmatched if len(squash(c)) >= 6}
    cards = 0
    tu_cards = 0
    annex_cards = 0
    tu = Counter()
    for line in open("certs.jsonl", encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        d = rec.get("data") or {}
        cards += 1
        text = " ".join(all_strings(d)).lower()
        toks = norm_tokens(text)
        for c in toks & unmatched:
            found[c] += 1
        if TU_RE.search(text):
            tu_cards += 1
            for m in TU_RE.findall(text):
                tu[m.strip()] += 1
        if ANNEX_RE.search(text):
            annex_cards += 1
        # separator-tolerant: squashed containment on UNREAD fields (compact)
        ur = unread_text(d)
        if ur:
            utoks = norm_tokens(ur)
            for c in utoks & unmatched:
                found_unread_tok[c] += 1
            sq = squash(ur)
            for c in (usep | long_un):
                cs = squash(c)
                if len(cs) >= 6 and cs in sq:
                    found_squash[c] += 1
        if cards % 1000 == 0:
            print(f"  ...{cards} cards, token-hits={len(found)}, "
                  f"unread-token-hits={len(found_unread_tok)}, "
                  f"squash-hits={len(found_squash)}", flush=True)

    print(f"cards={cards} cards_with_TU={tu_cards} "
          f"cards_annex_only={annex_cards}")
    print(f"distinct TU: {len(tu)}; top:")
    for t, n in tu.most_common(12):
        print(f"   {n:5d}  {t}")

    print(f"\nunmatched codes found as TOKEN in some card: {len(found)}")
    print(f"unmatched codes in UNREAD fields only: {len(found_unread_tok)}")
    print(f"unmatched codes found SQUASHED in some card:  {len(found_squash)}")
    extra = {c for c in found_squash if c not in found}
    print(f"  of which NOT found as token (separator/format miss): {len(extra)}")
    for c in list(extra)[:15]:
        print(f"    {c}   (brand={ubrand.get(c)!r})")
    json.dump({"token": dict(found), "unread_token": dict(found_unread_tok),
               "squash": dict(found_squash)},
              open("/tmp/unmatched_in_cards.json", "w"), ensure_ascii=False)


if __name__ == "__main__":
    main()