#!/bin/bash
# Very gentle reachability check: one TCP connect every 3 minutes.
while true; do
  if nc -z -G 5 212.164.138.20 443 >/dev/null 2>&1; then
    echo "$(date '+%H:%M:%S') tcp_ok"
    break
  else
    echo "$(date '+%H:%M:%S') down"
  fi
  sleep 180
done
