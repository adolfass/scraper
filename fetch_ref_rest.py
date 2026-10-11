#!/usr/bin/env python3
"""Resolve the 62 legacy-id ref declarations: number -> current index id ->
detail (to learn their idTechnicalReglaments for the scan TR set).

Gentle + resumable -> ref_rest.jsonl ({ref_id, id, data|null, note}).
"""
import json, os, time

import fsa_api

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "ref_rest.jsonl")
DELAY = 0.7


def have():
    out = set()
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            for line in f:
                try:
                    out.add(json.loads(line)["ref_id"])
                except Exception:
                    pass
    return out


def main():
    rest = json.load(open(os.path.join(ROOT, "ref_rest_ids.json"),
                          encoding="utf-8"))
    done = have()
    todo = [(int(k), v) for k, v in sorted(rest.items()) if int(k) not in done]
    print(f"legacy ref ids: {len(rest)}, cached: {len(done)}, "
          f"todo: {len(todo)}", flush=True)

    for n, (ref_id, num) in enumerate(todo, 1):
        rec = {"ref_id": ref_id, "number": num}
        # 1) find the current index row by exact number
        try:
            st, res = fsa_api.search_certificates(
                page=0, size=10,
                columns_search=[{"column": "number", "search": num}])
        except Exception as e:
            rec.update(note=f"search err {e}")
            res = {}
        items = res.get("items", []) if isinstance(res, dict) else []
        exact = [i for i in items if str(i.get("number", "")) == num]
        time.sleep(DELAY)
        if not exact:
            rec.update(note="not in index", n_hits=len(items))
        else:
            rec["id"] = exact[0]["id"]
            # 2) detail by current id -> TR ids
            try:
                st2, data = fsa_api.get_certificate(rec["id"])
                if st2 == 200:
                    rec["data"] = data
                else:
                    rec["note"] = f"detail http {st2}"
            except Exception as e:
                rec["note"] = f"detail err {e}"
            time.sleep(DELAY)
        with open(OUT, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        if n % 10 == 0:
            print(f"  {n}/{len(todo)}", flush=True)
    print("done", flush=True)


if __name__ == "__main__":
    main()
