#!/usr/bin/env bash
#
# Weekly-ish prediction run. Safe to run daily: fixtures that are already
# stored are refreshed, and anything already settled is left frozen.
#
# flock means two runs can never overlap. A long download must not race a
# second invocation into the same SQLite file.
#
source "$(dirname "$0")/env.sh"

exec 200>"$LOCK_DIR/football-run.lock"
if ! flock -n 200; then
  echo "$(date -Is) another prediction run is still going; skipping" >> "$LOG_DIR/run.log"
  exit 0
fi

{
  echo "===== $(date -Is) prediction run starting ====="
  "$VENV/bin/python" -m engine.run
  echo "===== $(date -Is) prediction run finished ok ====="
} >> "$LOG_DIR/run.log" 2>&1
