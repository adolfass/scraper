#!/bin/bash
# Phase 4: carry verified ref links (+~7.8k rows), rebuild, validate, report.
set -e
set -o pipefail
cd /Users/mac/project/exel
L=chain4.log
say() { echo "[$(date '+%H:%M:%S')] $*" >> "$L"; }

say "=== phase4 start ==="

say "STEP ref_carry (verify 119 ref urls by number)"
DELAY=1.0 .venv/bin/python ref_carry.py 2>&1 | tee -a "$L"

say "STEP build RULE=mix (with ref links)"
RULE=mix .venv/bin/python build_output.py 2>&1 | tee -a "$L"

say "STEP validate"
.venv/bin/python build_output.py validate 2>&1 | tee -a "$L"

say "STEP trial_report 500"
.venv/bin/python trial_report.py 500 2>&1 | tee -a "$L"

say "=== PHASE4 COMPLETE ==="
