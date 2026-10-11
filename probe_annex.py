#!/usr/bin/env python3
"""Probe whether the FSA registry exposes the ANNEX / BLANK contents (the part
of a certificate where the real article list lives, e.g. "согласно приложению -
бланк № ...").  78% of our downloaded cards are annex-only, so if these
documents are retrievable this is the single biggest lever left.

Run:  set -a; . ./.env; set +a; .venv/bin/python probe_annex.py
"""
import os
import re
import sys

import fsa_api

CERT_ID = 3630036      # has annexes: idAnnex 1327573/1327574, blanks 131926529/131926530
IANNEX = 1327573
IBLANK = 131926529

PATHS = [
    f"/api/v1/rss/common/certificates/{CERT_ID}/annexes",
    f"/api/v1/rss/common/certificates/{CERT_ID}/annex",
    f"/api/v1/rss/common/certificates/{CERT_ID}/blanks",
    f"/api/v1/rss/common/certificates/annex/{IANNEX}",
    f"/api/v1/rss/common/certificates/annexes/{IANNEX}",
    f"/api/v1/rss/common/annex/{IANNEX}",
    f"/api/v1/rss/common/annexes/{IANNEX}",
    f"/api/v1/rss/common/blanks/{IBLANK}",
    f"/api/v1/rss/common/blank/{IBLANK}",
    f"/api/v1/rss/common/certificates/blank/{IBLANK}",
    f"/api/v1/rss/common/files/{IBLANK}",
    f"/api/v1/rss/common/documents/{IBLANK}",
    f"/api/v1/files/{IBLANK}",
]


def main():
    print("token:", "yes" if fsa_api.login() else "no")
    for p in PATHS:
        try:
            st, data = fsa_api._call("GET", p, retries=1)
        except Exception as e:
            print(f"  {st_dash()}  {p}  -> ERR {e}")
            continue
        body = data if isinstance(data, str) else repr(data)
        head = re.sub(r"\s+", " ", str(body))[:160]
        print(f"  {st:>4}  {p}\n         {head}")


def st_dash():
    return "----"


if __name__ == "__main__":
    main()
