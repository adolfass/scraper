#!/bin/bash
# Phase 5: restore TNVED from displayed certs, rebuild, validate, report.
set -e
set -o pipefail
cd /Users/mac/project/exel
L=chain5.log
say() { echo "[$(date '+%H:%M:%S')] $*" >> "$L"; }

say "=== phase5 start ==="

say "STEP ref_carry_tnved (fetch missing details, resolve ids, patch entries)"
DELAY=1.0 .venv/bin/python ref_carry_tnved.py 2>&1 | tee -a "$L"

say "STEP build RULE=mix (with TNVED restored)"
RULE=mix .venv/bin/python build_output.py 2>&1 | tee -a "$L"

say "STEP validate"
.venv/bin/python build_output.py validate 2>&1 | tee -a "$L"

say "STEP trial_report 500"
.venv/bin/python trial_report.py 500 2>&1 | tee -a "$L"

say "=== PHASE5 COMPLETE ==="
