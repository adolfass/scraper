#!/bin/bash
# Self-driving pipeline: wait for main probe -> re-probe short codes
# (FORCE + ONLY_LEN_BELOW) -> build the final result file.
# Runs detached; logs to ip_run_all.log
cd /Users/mac/project/exel || exit 1
LOG=ip_run_all.log
exec >> "$LOG" 2>&1

echo "=== $(date '+%F %T') driver start ==="

# 1) wait for the main probe process to finish
while pgrep -f "ip_probe.py" >/dev/null 2>&1; do
  sleep 15
done
echo "=== $(date '+%F %T') main probe done ==="

# 2) re-probe short codes (<5 chars) with FORCE so the size=1 logic reruns
DELAY=1 FORCE=1 ONLY_LEN_BELOW=5 .venv/bin/python ip_probe.py
echo "=== $(date '+%F %T') short-code re-probe done, rc=$? ==="

# 3) build the final result file (brand gate -> details -> xlsx)
for run in 1 2 3; do
  DELAY=1 .venv/bin/python ip_build.py && break
  echo "=== $(date '+%F %T') ip_build attempt $run failed, retrying ==="
  sleep 60
done

echo "=== $(date '+%F %T') all done ==="