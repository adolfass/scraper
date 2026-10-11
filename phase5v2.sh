#!/bin/bash
# Phase 5v2: restore TNVED from registry cards, rebuild, validate, report.
set -e
set -o pipefail
cd /Users/mac/project/exel
L=chain5v2.log
say() { echo "[$(date '+%H:%M:%S')] $*" >> "$L"; }

say "=== phase5v2 start ==="
DELAY=1.0 .venv/bin/python ref_carry_tnved.py 2>&1 | tee -a "$L"
say "STEP build RULE=mix"
RULE=mix .venv/bin/python build_output.py 2>&1 | tee -a "$L"
say "STEP validate"
.venv/bin/python build_output.py validate 2>&1 | tee -a "$L"
say "STEP trial 500"
.venv/bin/python trial_report.py 500 2>&1 | tee -a "$L"
say "=== PHASE5v2 COMPLETE ==="
