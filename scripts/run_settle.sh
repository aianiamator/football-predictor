#!/usr/bin/env bash
#
# Fill in results for matches that have finished. This is what makes the
# public track record real, so it runs more often than the prediction job.
#
# It only ever writes results for finished matches and never modifies a stored
# forecast - enforced by a trigger in the database, not by this script.
#
source "$(dirname "$0")/env.sh"

exec 200>"$LOCK_DIR/football-settle.lock"
if ! flock -n 200; then
  echo "$(date -Is) another settle run is still going; skipping" >> "$LOG_DIR/settle.log"
  exit 0
fi

{
  echo "===== $(date -Is) settle starting ====="
  "$VENV/bin/python" -m engine.settle
  echo "===== $(date -Is) settle finished ok ====="
} >> "$LOG_DIR/settle.log" 2>&1
