#!/bin/bash
# Phase 2: retry missing cert details, archive RULE=t output,
# build+validate+report with RULE=any for comparison.
set -e
set -o pipefail
cd /Users/mac/project/exel
L=chain2.log
say() { echo "[$(date '+%H:%M:%S')] $*" >> "$L"; }

say "=== phase2 start ==="

say "STEP details retry (2 missing)"
PROBE_LOG=probe_log_all.jsonl SEARCH_ROWS=search_rows_all.jsonl DELAY=1.0 \
  .venv/bin/python pipeline.py details 2>&1 | tee -a "$L"

say "STEP archive RULE=t output"
cp Результат.xlsx Результат_rule_t.xlsx
say "archived to Результат_rule_t.xlsx"

say "STEP build RULE=any"
RULE=any .venv/bin/python build_output.py 2>&1 | tee -a "$L"

say "STEP validate RULE=any"
.venv/bin/python build_output.py validate 2>&1 | tee -a "$L"

say "STEP trial_report 500 (any)"
.venv/bin/python trial_report.py 500 2>&1 | tee -a "$L"

say "=== PHASE2 COMPLETE ==="
