#!/usr/bin/env python3
"""Self-healing supervisor for the Итоговый ИП pipeline.

- Phase A: keep ip_probe.py alive until every input code has been probed
  (restarts it if the OS/session kills it; progress is resumable).
- Phase B: re-probe short codes (<5 chars) with FORCE (size=1 path).
- Phase C: run ip_build.py (brand gate -> cert details -> xlsx), retrying.

Runs detached (see launch); appends to ip_run_all.log.
"""
import json, os, subprocess, time, resource

ROOT = "/Users/mac/project/exel"
SRC = "/Users/mac/Downloads/Итоговый ИП.xlsx"
PROBE = os.path.join(ROOT, "ip_probe_log.jsonl")
LOG = os.path.join(ROOT, "ip_run_all.log")
os.chdir(ROOT)


def log(msg):
    line = f"{time.strftime('%F %T')} {msg}\n"
    with open(LOG, "a") as f:
        f.write(line)
    print(line, end="", flush=True)


def set_limits():
    try:
        resource.setrlimit(resource.RLIMIT_NOFILE, (8192, 8192))
    except Exception:
        pass


def launch(script, env_extra, logfile):
    env = dict(os.environ)
    env.update(env_extra)
    f = open(os.path.join(ROOT, logfile), "ab", buffering=0)
    return subprocess.Popen(
        [".venv/bin/python", script],
        stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
        cwd=ROOT, env=env, start_new_session=True, preexec_fn=set_limits)


def input_codes():
    import openpyxl
    wb = openpyxl.load_workbook(SRC, read_only=True, data_only=True)
    ws = wb["Лист1"]
    s = set()
    for r in ws.iter_rows(values_only=True):
        c = str(r[1] or "").strip().lower() if r[1] is not None else ""
        if c:
            s.add(c)
    wb.close()
    return s


def probed_codes():
    """Latest record per code (later lines win)."""
    latest = {}
    try:
        with open(PROBE) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                    latest[r["p"]] = r
                except Exception:
                    pass
    except FileNotFoundError:
        pass
    return latest


def errored_codes(latest):
    return {c for c, r in latest.items() if r.get("error")}


def main():
    log("supervisor start")
    codes = input_codes()
    PROBE_ENV = {"DELAY": "1", "SOCK_TIMEOUT": "30"}
    # Phase A: main probe, restart until all codes have a record
    restarts = 0
    while True:
        latest = probed_codes()
        missing = codes - set(latest)
        if not missing:
            log("phase A complete: all codes have a record")
            break
        p = launch("ip_probe.py", PROBE_ENV, "ip_probe.log")
        log(f"phase A: started ip_probe.py pid={p.pid}, missing={len(missing)}")
        p.wait()
        restarts += 1
        latest = probed_codes()
        missing = codes - set(latest)
        log(f"phase A: probe exited rc={p.returncode}, "
            f"missing={len(missing)}, restarts={restarts}")
        time.sleep(10)

    # Phase B: retry errored codes a few times as the server recovers
    for rnd in range(1, 4):
        latest = probed_codes()
        errs = errored_codes(latest)
        if not errs:
            log(f"phase B: no errors left after round {rnd - 1}")
            break
        p = launch("ip_probe.py", {**PROBE_ENV, "REPROBE_ERRORS": "1"},
                   "ip_probe.log")
        log(f"phase B: error re-probe round {rnd} pid={p.pid}, errors={len(errs)}")
        p.wait()
        latest = probed_codes()
        log(f"phase B: round {rnd} done rc={p.returncode}, "
            f"errors now={len(errored_codes(latest))}")

    # Phase B2: short-code re-probe (<5 chars) with FORCE
    p = launch("ip_probe.py",
               {**PROBE_ENV, "FORCE": "1", "ONLY_LEN_BELOW": "5"},
               "ip_probe.log")
    log(f"phase B2: short-code re-probe pid={p.pid}")
    p.wait()
    log(f"phase B2: done rc={p.returncode}")

    # Phase C: build the final file
    for attempt in range(1, 6):
        p = launch("ip_build.py", PROBE_ENV, "ip_build.log")
        log(f"phase C: ip_build attempt {attempt} pid={p.pid}")
        p.wait()
        rc = p.returncode
        log(f"phase C: ip_build rc={rc}")
        if rc == 0:
            break
        time.sleep(30)
    log("supervisor done")


if __name__ == "__main__":
    main()
