#!/usr/bin/env python3
"""Discover certificates for price-list article codes on pub.fsa.gov.ru.

Two-phase, gentle (strictly sequential, ~0.7s between requests, backoff on errors):

Phase "probe" - trie prefix probing over the article column:

  Registry search semantics (verified empirically):
    * query >= 3 chars  -> case-insensitive SUBSTRING match anywhere in
      productIdentificationArticle text;
    * query of 1-2 chars -> different (exact-token-ish) semantics, unreliable;
    * multi-word query  -> AND of the words; no OR, no wildcards (403 on "OR").
  Therefore any certificate containing a code also contains every prefix of that
  code (len >= 3), so probing by prefix yields a SUPERSET and is complete:
    - total == 0   -> no cert contains the prefix: whole group pruned (definitive)
    - else         -> either PAGE through all matching certs (stable id-ASC sort,
                      ceil(total/100) requests, complete candidate set, matched
                      locally against full article texts) or SPLIT the code group
                      by the next character - whichever is cheaper
                      (page_cost <= number of child groups -> page).
  Codes equal to a split prefix (or shorter than 3 chars) get an exact probe.

  Local matching records TWO rules per (code, cert) pair:
    "t" - code equals a delimited item of the article list (exact item);
    "s" - code occurs as substring only.
  Validation against Готовый.xlsx decides which rule reproduces the reference.

Phase "details" - fetch certificate details only for certs actually selected for
  at least one code (needed for per-identification TNVED codes).

Usage:
  .venv/bin/python pipeline.py probe [N]   # N = trial sample size (optional)
  .venv/bin/python pipeline.py scan 30,5,8 [step_days]
                                           # complete scan filtered by TR ids,
                                           # date-sliced (page <= 20 => 2100
                                           # rows max per query), resumable
  .venv/bin/python pipeline.py details
  .venv/bin/python pipeline.py stats
"""
import json, os, re, sys, threading, time
from collections import defaultdict, deque, Counter

import fsa_api

ROOT = os.path.dirname(os.path.abspath(__file__))
PROBE_LOG = os.environ.get("PROBE_LOG") or os.path.join(ROOT, "probe_log.jsonl")
SEARCH_ROWS = os.environ.get("SEARCH_ROWS") or os.path.join(ROOT, "search_rows.jsonl")
CERTS_LOG = os.environ.get("CERTS_LOG") or os.path.join(ROOT, "certs.jsonl")

MAX_LEAF = 100             # registry page size == max complete leaf
DELAY = float(os.environ.get("DELAY", "0.7"))   # pause between requests, seconds
BACKOFF_BASE = float(os.environ.get("BACKOFF_BASE", "5"))
BACKOFF_MAX = float(os.environ.get("BACKOFF_MAX", "45"))
MAX_ATTEMPTS = int(os.environ.get("MAX_ATTEMPTS", "4"))
ARTICLE_COLUMN = "productIdentificationArticle"
TOKEN_SPLIT = re.compile(r"[;,\s]+")

_lock = threading.Lock()


def _append(path, obj):
    line = json.dumps(obj, ensure_ascii=False)
    with _lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def load_jsonl(path, key=None):
    out = {} if key else []
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if key:
                out[r[key]] = r
            else:
                out.append(r)
    return out


# ------------------------------------------------------------------ registry ops
_consec_fail = [0]
_backoff = [BACKOFF_BASE]


class QueryError(Exception):
    """Server rejected this particular query (400/403) - do not retry."""


def _sleep():
    if DELAY:
        time.sleep(DELAY)


def polite(fn, what=""):
    """Call fn with bounded exponential backoff on server errors.

    The FSA server randomly stalls ~1 in 6 requests; we cap the per-request
    timeout and retry a few times, then give up (SystemExit) so the caller can
    record the code and move on instead of sleeping for minutes.
    """
    attempt = 0
    # growing per-attempt socket timeout: short to abandon random stalls fast,
    # longer on retries to catch genuinely heavy (slow) registry queries.
    sched = [float(x) for x in
             os.environ.get("TIMEOUT_SCHED", "20,25,45,70").split(",")]
    while True:
        try:
            fsa_api.TIMEOUT = sched[min(attempt, len(sched) - 1)]
            res = fn()
            _consec_fail[0] = 0
            _backoff[0] = BACKOFF_BASE
            return res
        except QueryError:
            raise
        except Exception as e:
            msg = str(e)
            transient = any(x in msg for x in
                            ("429", "503", "502", "500", "408", "timed out",
                             "unreachable", "Broken pipe", "Connection reset",
                             "DDoS", "stalled", "handshake"))
            if not transient:
                raise
            attempt += 1
            _consec_fail[0] += 1
            if attempt >= MAX_ATTEMPTS:
                print(f"  gave up on {what} after {attempt} attempts ({msg[:70]})",
                      flush=True)
                raise SystemExit(3)
            wait = min(BACKOFF_BASE * (2 ** (attempt - 1)), BACKOFF_MAX)
            print(f"  transient error {what} ({msg[:90]}), sleeping {wait:.0f}s",
                  flush=True)
            time.sleep(wait)


def _search(prefix, page, size):
    def _do():
        _sleep()
        st, res = fsa_api.search_certificates(
            page=page, size=size,
            columns_sort=[{"column": "id", "sort": "ASC"}],
            columns_search=[{"column": ARTICLE_COLUMN, "search": prefix}])
        if st in (400, 403):
            raise QueryError(f"http {st} for prefix {prefix!r}")
        if st != 200:
            raise RuntimeError(f"search http {st}")
        return res
    return polite(_do, what=prefix)


def probe_prefix(prefix):
    """Page 0 only. Returns (total, rows, size_used).

    size=100 for prefixes >= 5 chars (usually a complete leaf in one request),
    size=1 for shallow prefixes (usually a split; rows not needed).
    """
    size = 100 if len(prefix) >= 5 else 1
    res = _search(prefix, 0, size)
    return res.get("total", 0), res.get("items", []), size


def fetch_all_rows(prefix, total, have=None, have_size=None):
    """Complete row set via stable id-ASC paging (<=100 rows per request)."""
    rows = list(have) if (have_size == 100 and have) else []
    page = 1 if rows else 0
    while len(rows) < total:
        res = _search(prefix, page, 100)
        items = res.get("items", [])
        if not items:
            break
        rows.extend(items)
        if len(items) < 100:
            break
        page += 1
        if page > 500:
            raise RuntimeError(f"paging runaway for {prefix!r} total={total}")
    seen, out = set(), []
    for r in rows:
        rid = r.get("id")
        if rid is not None and rid not in seen:
            seen.add(rid)
            out.append(r)
    return out


def get_cert(cert_id):
    def _do():
        _sleep()
        st, res = fsa_api.get_certificate(cert_id)
        if st != 200:
            raise RuntimeError(f"cert {cert_id} http {st}")
        return res
    return polite(_do, what=f"cert {cert_id}")


# ----------------------------------------------------------- declarations (rds)
def search_decl(article, page, size):
    def _do():
        _sleep()
        st, res = fsa_api.search_declarations(
            columns_search=[{"name": fsa_api.DECL_ARTICLE_COLUMN,
                             "search": article, "type": 0}],
            size=size, page=page)
        if st in (400, 403):
            raise QueryError(f"http {st} decl {article!r}")
        if st != 200:
            raise RuntimeError(f"decl search http {st}")
        return res
    return polite(_do, what=f"decl {article}")


def get_decl(decl_id):
    def _do():
        _sleep()
        st, res = fsa_api.get_declaration(decl_id)
        if st != 200:
            raise RuntimeError(f"decl {decl_id} http {st}")
        return res
    return polite(_do, what=f"decl {decl_id}")


# ------------------------------------------------------------------ local match
def row_summary(row):
    return {"id": row.get("id"),
            "number": (row.get("number") or "").strip(),
            "date": row.get("date") or "",
            "endDate": row.get("endDate") or "",
            "idStatus": row.get("idStatus"),
            "certType": row.get("certType") or ""}


def local_matches(codes_set, rows, summaries_seen):
    """Match the group's codes against leaf rows.

    Returns list of [code, cert_id, rule] with rule "t" (exact item) or
    "s" (substring only).
    """
    matches = []
    for row in rows:
        rid = row.get("id")
        if rid is None:
            continue
        if rid not in summaries_seen:
            _append(SEARCH_ROWS, row_summary(row))
            summaries_seen.add(rid)
        art = row.get(ARTICLE_COLUMN) or ""
        if not art:
            continue
        art_l = art.lower()
        toks = None
        for code in codes_set:
            if code in art_l:
                if toks is None:
                    toks = set(TOKEN_SPLIT.split(art_l)) - {""}
                matches.append([code, rid, "t" if code in toks else "s"])
    return matches


# ------------------------------------------------------------------------ probe
def load_codes():
    import openpyxl
    print("loading codes...", flush=True)
    wb = openpyxl.load_workbook(os.path.join(ROOT, "Исходный.xlsx"),
                                read_only=True, data_only=True)
    ws = wb["PRICE"]
    hdr = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    code_idx = hdr.index("Code")
    codes = set()
    for row in ws.iter_rows(min_row=2, values_only=True):
        v = row[code_idx]
        if v is None:
            continue
        s = str(v).strip()
        if s:
            codes.add(s.lower())
    wb.close()
    print(f"unique codes: {len(codes)}", flush=True)
    return codes


def handle_node(prefix, cs, log, summaries_seen, deferred):
    """Probe one trie node; returns its log record (already appended).

    Decision rule at total > 0:
      - page_cost = ceil(total/100) requests for a COMPLETE candidate set
      - groups = distinct child prefixes (split cost baseline: >=len(groups))
      page when paging is at least as cheap (or a code equals the prefix, or
      there is nothing to split by), otherwise split deeper.
    """
    total, rows, size_used = probe_prefix(prefix)
    if total == 0:
        rec = {"p": prefix, "kind": "zero", "total": 0}
    else:
        groups = {c[:len(prefix) + 1] for c in cs if len(c) > len(prefix)}
        has_atomic = any(len(c) == len(prefix) for c in cs)
        page_cost = -(-total // MAX_LEAF)
        complete = (size_used == 100 and len(rows) >= total)
        if total <= MAX_LEAF or has_atomic or not groups or page_cost <= len(groups):
            if not complete:
                rows = fetch_all_rows(prefix, total, rows, size_used)
            matches = local_matches(set(cs), rows, summaries_seen)
            rec = {"p": prefix, "kind": "leaf", "total": total,
                   "ids": [r.get("id") for r in rows], "matches": matches}
            if len(rows) < total:
                rec["note"] = f"rows {len(rows)} < total {total}"
        else:
            rec = {"p": prefix, "kind": "split", "total": total}
    _append(PROBE_LOG, rec)
    log[prefix] = rec
    return rec


def split_node(prefix, cs, groups, deferred):
    for c in cs:
        if len(c) > len(prefix):
            groups[c[:len(prefix) + 1]].append(c)
        else:
            deferred.add(c)


def run_probe(sample=None):
    codes = load_codes()
    if sample:
        import random
        rnd = random.Random(42)
        codes = set(rnd.sample(sorted(codes), min(sample, len(codes))))
        print(f"TRIAL RUN on {len(codes)} codes", flush=True)

    log = load_jsonl(PROBE_LOG, key="p")
    summaries_seen = set(load_jsonl(SEARCH_ROWS, key="id"))
    print(f"probe log: {len(log)} records, row summaries: {len(summaries_seen)}",
          flush=True)

    deferred = set()
    nodes = defaultdict(list)
    for c in codes:
        if len(c) >= 3:
            nodes[c[:3]].append(c)
        else:
            deferred.add(c)

    queue = deque(sorted(nodes.items()))
    done_nodes = 0
    stats = Counter()
    tries = Counter()

    while queue:
        batch = []
        while queue and len(batch) < 30:
            batch.append(queue.popleft())
        for prefix, cs in batch:
            rec = log.get(prefix)
            if rec is None:
                try:
                    rec = handle_node(prefix, cs, log, summaries_seen, deferred)
                except QueryError as e:
                    tries[prefix] += 1
                    if tries[prefix] < 5:
                        print(f"  node {prefix!r} rejected ({e}), "
                              f"retry {tries[prefix]}/4", flush=True)
                        queue.append((prefix, cs))
                        time.sleep(10)
                        continue
                    rec = {"p": prefix, "kind": "err", "error": str(e)}
                    _append(PROBE_LOG, rec)
                    log[prefix] = rec
                except SystemExit:
                    raise
                except Exception as e:
                    tries[prefix] += 1
                    if tries[prefix] < 5:
                        print(f"  node {prefix!r} error, requeue "
                              f"{tries[prefix]}/4: {e}", flush=True)
                        queue.append((prefix, cs))
                        time.sleep(5)
                        continue
                    rec = {"p": prefix, "kind": "err", "error": str(e)}
                    _append(PROBE_LOG, rec)
                    log[prefix] = rec
            done_nodes += 1
            stats[rec["kind"]] += 1
            if rec["kind"] == "split":
                groups = defaultdict(list)
                split_node(prefix, cs, groups, deferred)
                for g, gc in groups.items():
                    if g in log and log[g]["kind"] == "leaf":
                        stats["leaf_cached"] += 1
                    else:
                        queue.append((g, gc))
        if done_nodes % 30 == 0 or not queue:
            print(f"nodes={done_nodes} queue={len(queue)} "
                  f"leaves={stats['leaf']} zero={stats['zero']} "
                  f"split={stats['split']} err={stats['err']} "
                  f"deferred={len(deferred)}", flush=True)

    # exact probes: codes shorter than 3 chars, or equal to a split prefix
    print(f"exact probes: {len(deferred)}", flush=True)
    for i, c in enumerate(sorted(deferred), 1):
        key = "exact:" + c
        if key not in log:
            try:
                total, rows, size_used = probe_prefix(c)
                if total > MAX_LEAF:
                    rows = fetch_all_rows(c, total, rows, size_used)
            except QueryError as e:
                rec = {"p": key, "kind": "err", "error": str(e)}
                _append(PROBE_LOG, rec); log[key] = rec
                continue
            except SystemExit:
                raise
            except Exception as e:
                print(f"  exact {c!r} error: {e}", flush=True)
                time.sleep(5)
                continue
            if total == 0:
                rec = {"p": key, "kind": "zero", "total": 0}
            else:
                matches = local_matches({c}, rows, summaries_seen)
                rec = {"p": key, "kind": "leaf", "total": total,
                       "ids": [r.get("id") for r in rows], "matches": matches}
                if len(rows) < total:
                    rec["note"] = f"rows {len(rows)} < total {total}"
            _append(PROBE_LOG, rec)
            log[key] = rec
        if i % 100 == 0:
            print(f"  exact {i}/{len(deferred)}", flush=True)

    total_matches = sum(len(r.get("matches", [])) for r in log.values())
    matched_codes = set(m[0] for r in log.values() for m in r.get("matches", []))
    rules = Counter(m[2] for r in log.values() for m in r.get("matches", []))
    print(f"probe complete: nodes={done_nodes} leaves={stats['leaf']} "
          f"zero={stats['zero']} split={stats['split']} err={stats['err']} "
          f"matches={total_matches} distinct codes matched={len(matched_codes)} "
          f"rules={dict(rules)}", flush=True)


# ------------------------------------------------------------------------ scan
# Complete registry scan filtered by technical regulation ids (idTechReg),
# date-sliced because the server rejects page > 20 (max 2100 rows per query).
# Slice bounds overlap by 2 days so no certificate can fall between slices
# regardless of date-bound inclusivity; duplicates are removed via pairs_seen.
PAGE_LIMIT = 20
SLICE_MAX = (PAGE_LIMIT + 1) * MAX_LEAF        # 2100 rows


def _scan_req(dmin, dmax, tr_ids, page, size):
    extra = {"idTechReg": list(tr_ids),
             "regDate": {"minDate": dmin, "maxDate": dmax}}

    def _do():
        _sleep()
        st, res = fsa_api.search_certificates(
            page=page, size=size,
            columns_sort=[{"column": "id", "sort": "ASC"}],
            extra_filter=extra)
        if st in (400, 403):
            raise QueryError(f"http {st} scan {dmin}..{dmax} p{page}")
        if st != 200:
            raise RuntimeError(f"scan http {st}")
        return res
    return polite(_do, what=f"scan {dmin}..{dmax} p{page}")


def registry_date_bounds():
    out = []
    for s in ("ASC", "DESC"):
        def _do():
            _sleep()
            st, res = fsa_api.search_certificates(
                page=0, size=1, columns_sort=[{"column": "date", "sort": s}])
            if st != 200:
                raise RuntimeError(f"bounds http {st}")
            return res
        r = polite(_do, what="date bounds")
        items = r.get("items") or []
        out.append(str(items[0].get("date") or "")[:10] if items else None)
    return out[0], out[1]


def match_row_tokens(codes_set, odd_codes, rows, summaries_seen, pairs_seen):
    """Token-equality matching ('t') for normal codes + substring ('s') only for
    codes that contain the token-split characters (space/comma) themselves."""
    matches = []
    for row in rows:
        rid = row.get("id")
        if rid is None:
            continue
        if rid not in summaries_seen:
            _append(SEARCH_ROWS, row_summary(row))
            summaries_seen.add(rid)
        art = (row.get(ARTICLE_COLUMN) or "").lower()
        if not art:
            continue
        for t in TOKEN_SPLIT.split(art):
            if t and t in codes_set and (t, str(rid)) not in pairs_seen:
                pairs_seen.add((t, str(rid)))
                matches.append([t, rid, "t"])
        for c in odd_codes:
            if c in art and (c, str(rid)) not in pairs_seen:
                pairs_seen.add((c, str(rid)))
                matches.append([c, rid, "s"])
    return matches


def run_scan(tr_ids, step_days=365):
    from datetime import datetime, timedelta
    from collections import deque

    tr_ids = sorted(int(x) for x in tr_ids)
    # state is tagged per TR-set: later passes over other TR ids do not collide
    tag = "-".join(str(x) for x in tr_ids)
    codes = load_codes()
    odd = sorted(c for c in codes if ("," in c or " " in c))
    print(f"odd codes (space/comma): {len(odd)}", flush=True)

    log = load_jsonl(PROBE_LOG, key="p")
    summaries_seen = set(load_jsonl(SEARCH_ROWS, key="id"))
    pairs_seen = set()
    for rec in log.values():
        for m in rec.get("matches", []):
            pairs_seen.add((m[0], str(m[1])))
    done = {k.split("|", 1)[1] for k in log
            if k.startswith(f"scandone|{tag}|")}
    print(f"resume: {len(log)} records, {len(done)} slices done, "
          f"{len(pairs_seen)} pairs known", flush=True)

    lo, hi = registry_date_bounds()
    print(f"registry date range: {lo} .. {hi} | TR ids: {tr_ids}", flush=True)
    d0 = datetime.strptime(os.environ.get("SCAN_START") or lo or "2010-01-01",
                           "%Y-%m-%d").date()
    d1 = datetime.strptime(os.environ.get("SCAN_END") or hi or "2026-12-31",
                           "%Y-%m-%d").date()
    print(f"scan window: {d0} .. {d1}", flush=True)

    def iso(d):                              # date/datetime object or str
        return d.isoformat() if hasattr(d, "isoformat") else str(d)

    # Lazy cursor over top-level date slices + job queue for binary splits.
    # Empty stretches (registry dates start in year 0201 - data entry
    # artifacts) are skipped with a step growing 4x, so the empty millennium
    # costs ~10 probes instead of ~1800.
    def advance(x, y):                       # 2-day overlap, always progresses
        nxt = y - timedelta(days=2)
        return nxt if nxt > x else x + timedelta(days=1)

    jobs = deque()
    cursor, step, empty_run = d0, step_days, 0
    stats = Counter()

    # Peer workers scan other date partitions into their own state files.
    # Every 3 minutes import their scandone/scan records so nobody redoes
    # work another worker already finished (or is mid-way through).
    peers = [p.strip() for p in os.environ.get("SCAN_PEERS", "").split(",")
             if p.strip() and os.path.abspath(p) != os.path.abspath(PROBE_LOG)]
    last_peer = 0.0
    if peers:
        print(f"peer state files: {peers}", flush=True)

    while cursor <= d1 or jobs:
        if peers and time.time() - last_peer > 180:
            last_peer = time.time()
            for pf in peers:
                if not os.path.exists(pf):
                    continue
                for k, v in load_jsonl(pf, key="p").items():
                    if k in log or v.get("kind") not in ("scandone", "scan"):
                        continue
                    log[k] = v
                    for m in v.get("matches", []):
                        pairs_seen.add((m[0], str(m[1])))
        if jobs:
            a, b, top = *jobs.popleft(), False
        else:
            a, b, top = cursor, min(cursor + timedelta(days=step), d1), True
        key = f"{a}|{b}"
        if f"scandone|{tag}|{key}" in log:
            stats["skip"] += 1
            if top:
                cursor = advance(cursor, b)
            continue

        res = None
        for attempt in range(3):
            try:
                res = _scan_req(iso(a), iso(b), tr_ids, 0, 100)
                break
            except QueryError as e:
                print(f"  slice {key} rejected ({e}), retry", flush=True)
                time.sleep(10)
        if res is None:
            rec = {"p": f"scanerr|{tag}|{key}", "kind": "scanerr"}
            _append(PROBE_LOG, rec)
            log[rec["p"]] = rec
            stats["err"] += 1
            if top:
                cursor = advance(cursor, b)
            continue

        total = res.get("total", 0)
        if top:
            if total == 0:
                empty_run += 1
                if empty_run >= 2:
                    step = min(step * 4, 7300)
            else:
                empty_run, step = 0, step_days
            cursor = advance(cursor, b)
        if total == 0:
            rec = {"p": f"scandone|{tag}|{key}", "kind": "scandone",
                   "total": 0}
            _append(PROBE_LOG, rec)
            log[rec["p"]] = rec
            stats["empty"] += 1
            continue

        if total > SLICE_MAX:
            if not isinstance(a, str) and b - a > timedelta(days=1):
                mid = a + (b - a) // 2
                jobs.append((a, mid + timedelta(days=1)))
                jobs.append((mid, b))
                stats["split"] += 1
            elif isinstance(a, str) and "T" in str(a):
                # datetime halves must never exceed SLICE_MAX; give up loudly
                rec = {"p": f"scanerr|{tag}|{key}", "kind": "scanerr",
                       "total": total}
                _append(PROBE_LOG, rec)
                log[rec["p"]] = rec
                stats["err"] += 1
                print(f"  !! slice {key} total={total} unsplit", flush=True)
            else:
                # single-day slice too big: split by time of day
                d = str(a)[:10]
                jobs.append((f"{d}T12:00:00", f"{d}T23:59:59"))
                jobs.append((f"{d}T00:00:00", f"{d}T11:59:59"))
                stats["split_dt"] += 1
            continue

        n_pages = -(-total // MAX_LEAF)
        for p in range(n_pages):
            rec_key = f"scan|{tag}|{key}|p{p}"
            if rec_key in log:
                continue
            if p == 0:
                rows = res.get("items", [])
            else:
                rows = None
                for attempt in range(3):
                    try:
                        rows = _scan_req(iso(a), iso(b), tr_ids, p, 100) \
                            .get("items", [])
                        break
                    except QueryError:
                        stats["page_retry"] += 1
                        time.sleep(10)
                if rows is None:
                    rec = {"p": f"scanerr|{tag}|{key}|p{p}",
                           "kind": "scanerr"}
                    _append(PROBE_LOG, rec)
                    log[rec["p"]] = rec
                    stats["page_err"] += 1
                    continue
            matches = match_row_tokens(codes, odd, rows, summaries_seen,
                                       pairs_seen)
            rec = {"p": rec_key, "kind": "scan", "total": total,
                   "n": len(rows), "matches": matches}
            _append(PROBE_LOG, rec)
            log[rec_key] = rec
            stats["pages"] += 1

        rec = {"p": f"scandone|{tag}|{key}", "kind": "scandone",
               "total": total}
        _append(PROBE_LOG, rec)
        log[rec["p"]] = rec
        stats["slices"] += 1
        if stats["slices"] % 20 == 0:
            print(f"slice done {key} total={total} | {dict(stats)} "
                  f"queue={len(jobs)} pairs={len(pairs_seen)}", flush=True)

    errs = [k for k in log if k.startswith(f"scanerr|{tag}|")]
    print(f"SCAN COMPLETE {dict(stats)} scanerrs={errs} "
          f"pairs={len(pairs_seen)}", flush=True)


# ------------------------------------------------------------------ phase: details
def selected_certs():
    """cert ids chosen for at least one code (newest active by date wins)."""
    rows = load_jsonl(SEARCH_ROWS, key="id")
    cand = defaultdict(set)
    for rec in load_jsonl(PROBE_LOG, key="p").values():
        for m in rec.get("matches", []):
            cand[m[0]].add(m[1])

    def sort_key(rid):
        r = rows.get(rid, {})
        active = 1 if r.get("idStatus") == 6 else 0
        return (active, str(r.get("date") or ""))

    chosen = {}
    for code, rids in cand.items():
        chosen[code] = max(rids, key=sort_key)
    return chosen


def source_codes(n=None):
    """Codes of the first n source rows (all rows when n is None)."""
    import openpyxl
    wb = openpyxl.load_workbook(os.path.join(ROOT, "Исходный.xlsx"),
                                read_only=True, data_only=True)
    ws = wb["PRICE"]
    it = ws.iter_rows(values_only=True)
    hdr = list(next(it))
    ci = hdr.index("Code")
    out = []
    for i, r in enumerate(it):
        if n is not None and i >= n:
            break
        out.append(str(r[ci]).strip().lower() if r[ci] else "")
    wb.close()
    return out


def run_details(limit_rows=None):
    chosen = selected_certs()
    certs = {k: v["data"] for k, v in load_jsonl(CERTS_LOG, key="id").items()
             if v.get("data") is not None}
    if limit_rows:
        # trial: first `limit_rows` source rows whose code already has a cert
        import openpyxl
        wb = openpyxl.load_workbook(os.path.join(ROOT, "Исходный.xlsx"),
                                    read_only=True, data_only=True)
        ws = wb["PRICE"]
        it = ws.iter_rows(values_only=True)
        hdr = list(next(it))
        ci = hdr.index("Code")
        picked, seen = [], set()
        for r in it:
            c = str(r[ci]).strip().lower() if r[ci] else ""
            if c and c in chosen and c not in seen:
                seen.add(c)
                picked.append(c)
                if len(picked) >= limit_rows:
                    break
        wb.close()
        need = sorted({chosen[c] for c in picked if chosen[c] not in certs})
        print(f"trial limit: {len(picked)} matched codes -> "
              f"{len(need)} certs to fetch", flush=True)
    else:
        need = sorted({cid for cid in chosen.values() if cid not in certs})
    # optional sharding: DETAIL_SPLIT="k/n" fetches need[k::n]
    split = os.environ.get("DETAIL_SPLIT", "")
    if split and "/" in split:
        k, n = (int(x) for x in split.split("/")[:2])
        need = need[k::n]
        print(f"DETAIL_SPLIT={split}: {len(need)} certs in this shard", flush=True)
    print(f"codes matched: {len(chosen)}, certs to fetch: {len(need)}", flush=True)
    for i, cid in enumerate(need, 1):
        try:
            data = get_cert(cid)
        except SystemExit:
            raise
        except Exception as e:
            print(f"  cert {cid} failed: {e}", flush=True)
            continue
        _append(CERTS_LOG, {"id": cid, "data": data})
        if i % 25 == 0:
            print(f"  details {i}/{len(need)}", flush=True)
    print("details complete", flush=True)


def stats():
    log = load_jsonl(PROBE_LOG, key="p")
    kinds = Counter(r.get("kind") for r in log.values())
    matches = sum(len(r.get("matches", [])) for r in log.values())
    matched = set(m[0] for r in log.values() for m in r.get("matches", []))
    rules = Counter(m[2] for r in log.values() for m in r.get("matches", [])
                    if len(m) > 2)
    rows = load_jsonl(SEARCH_ROWS, key="id")
    certs = load_jsonl(CERTS_LOG, key="id")
    print(f"probe records: {len(log)} {dict(kinds)}")
    print(f"match pairs: {matches}, distinct codes matched: {len(matched)}, "
          f"rules: {dict(rules)}")
    print(f"cert summaries: {len(rows)}, cert details: {len(certs)}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "stats"
    if cmd == "probe":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else None
        run_probe(sample=n)
    elif cmd == "details":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else None
        run_details(limit_rows=n)
    elif cmd == "scan":
        # args: comma-separated idTechReg list, optional slice step in days
        ids = [int(x) for x in sys.argv[2].split(",")]
        step = int(sys.argv[3]) if len(sys.argv) > 3 else 30
        run_scan(ids, step_days=step)
    elif cmd == "stats":
        stats()
    else:
        print(__doc__)
