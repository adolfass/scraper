#!/bin/bash
# Phase 3: archive RULE=any output, build+validate+report with RULE=mix
# (substring pairs only for complex codes) - the final variant.
set -e
set -o pipefail
cd /Users/mac/project/exel
L=chain3.log
say() { echo "[$(date '+%H:%M:%S')] $*" >> "$L"; }

say "=== phase3 start ==="

say "STEP archive RULE=any output"
cp Результат.xlsx Результат_rule_any.xlsx
say "archived to Результат_rule_any.xlsx"

say "STEP build RULE=mix"
RULE=mix .venv/bin/python build_output.py 2>&1 | tee -a "$L"

say "STEP validate RULE=mix"
.venv/bin/python build_output.py validate 2>&1 | tee -a "$L"

say "STEP trial_report 500 (mix)"
.venv/bin/python trial_report.py 500 2>&1 | tee -a "$L"

say "=== PHASE3 COMPLETE ==="
