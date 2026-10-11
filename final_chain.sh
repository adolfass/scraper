#!/bin/bash
# Final pipeline chain: waits for all scan workers to exit, then
# merge_state -> merge_all -> incremental details -> resolve_tnveds
# -> build (RULE=t) -> validate -> trial_report 500.
# Every step logs to chain.log with markers; aborts on first failure.
set -e
set -o pipefail
cd /Users/mac/project/exel
L=chain.log
say() { echo "[$(date '+%H:%M:%S')] $*" >> "$L"; }

say "=== chain started, waiting for scan workers ==="
while ps aux | grep -q "[p]ipeline.py scan"; do sleep 60; done
say "all scans exited"

say "STEP merge_state"
.venv/bin/python merge_state.py 2>&1 | tee -a "$L"

say "STEP merge_all"
.venv/bin/python merge_all.py 2>&1 | tee -a "$L"

say "STEP incremental details"
PROBE_LOG=probe_log_all.jsonl SEARCH_ROWS=search_rows_all.jsonl DELAY=1.0 \
  .venv/bin/python pipeline.py details 2>&1 | tee -a "$L"

say "STEP resolve_tnveds"
.venv/bin/python resolve_tnveds.py 2>&1 | tee -a "$L"

say "STEP build RULE=t"
RULE=t .venv/bin/python build_output.py 2>&1 | tee -a "$L"

say "STEP validate"
.venv/bin/python build_output.py validate 2>&1 | tee -a "$L"

say "STEP trial_report 500"
.venv/bin/python trial_report.py 500 2>&1 | tee -a "$L"

say "=== CHAIN COMPLETE ==="
