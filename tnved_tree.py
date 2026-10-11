#!/usr/bin/env python3
"""Download full TNVED tree from pub.fsa.gov.ru -> tnved_tree.json (id -> {code,name,leaf}).

Gentle: at most 2 concurrent requests with a pause; resumable (progress saved
continuously via an 'expanded' flag on each node).
"""
import json, os, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.request
import socket

# Some networks advertise broken IPv6 routes; force IPv4.
_orig_gai = socket.getaddrinfo
def _gai_v4(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_gai(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = _gai_v4

URL = "https://pub.fsa.gov.ru/nsi/api/tree/tnved/get"
OUT = "/Users/mac/project/exel/tnved_tree.json"
WORKERS = 2          # gentle on the registry
DELAY = 0.25         # pause per request
HDRS = {"accept": "application/json", "content-type": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"}

_last = [0.0]


def fetch(parent_id=None, retries=6):
    body = {"parentId": parent_id, "attrs": []} if parent_id is not None else {}
    data = json.dumps(body).encode()
    for a in range(retries):
        wait = DELAY - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        try:
            req = urllib.request.Request(URL, data=data, headers=HDRS, method="POST")
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read())["items"]
        except Exception as e:
            if a == retries - 1:
                print(f"FAIL parent={parent_id}: {e}", flush=True)
                return None          # signal failure (do not mark expanded)
            time.sleep(5 * (a + 1))
    return None


def save(nodes):
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(nodes, f, ensure_ascii=False)
    os.replace(tmp, OUT)


def main():
    nodes = {}
    if os.path.exists(OUT):
        try:
            nodes = json.load(open(OUT))
            print(f"resuming: {len(nodes)} nodes already downloaded", flush=True)
        except Exception:
            nodes = {}

    roots = fetch()
    if roots is None:
        print("cannot reach registry - abort", flush=True)
        return 1
    for n in roots:
        nodes.setdefault(n["id"], {"code": n.get("code"), "name": n.get("name", ""),
                                   "leaf": n.get("leaf", False)})
        nodes[n["id"]].setdefault("expanded", False)
    print(f"roots: {len(roots)}", flush=True)

    def queue_of(nodes):
        return [nid for nid, n in nodes.items()
                if not n.get("leaf") and not n.get("expanded")]

    depth = 0
    while True:
        pend = queue_of(nodes)
        if not pend:
            break
        depth += 1
        print(f"depth {depth}: {len(pend)} parents to expand", flush=True)
        failed = []
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futs = {ex.submit(fetch, pid): pid for pid in pend}
            done = 0
            for fut in as_completed(futs):
                pid = futs[fut]
                items = fut.result()
                done += 1
                if items is None:
                    failed.append(pid)
                    continue
                nodes[pid]["expanded"] = True
                for n in items:
                    if not isinstance(n, dict) or n.get("id") is None:
                        continue
                    e = nodes.setdefault(n["id"], {})
                    e.setdefault("code", n.get("code") or n.get("displayName", ""))
                    e.setdefault("name", n.get("name", ""))
                    e["leaf"] = bool(n.get("leaf"))
                    e.setdefault("expanded", False)
                    e["parent"] = n.get("parentId")
                if done % 25 == 0:
                    save(nodes)
                    print(f"  {done}/{len(pend)} expanded, nodes={len(nodes)}", flush=True)
        save(nodes)
        print(f"depth {depth} done: nodes={len(nodes)} failed={len(failed)}", flush=True)
        if failed and len(failed) == len(pend):
            print("all parents failed - network down, abort (resume later)", flush=True)
            return 1
        time.sleep(1)

    print(f"TOTAL {len(nodes)} -> {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
