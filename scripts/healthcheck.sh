#!/usr/bin/env bash
#
# Is it actually running?
#
# Run this by hand any time, or from cron to get an email when something has
# quietly stopped. Exits non-zero if anything is wrong, so it works as a
# monitoring probe without modification.
#
# The failure this is really guarding against is the silent one: the jobs keep
# running, exit 0, and publish nothing - so the site serves week-old forecasts
# and looks completely normal.
#
source "$(dirname "$0")/env.sh"

MAX_AGE_HOURS="${MAX_AGE_HOURS:-30}"   # a daily job that missed one run
fail=0

# The venv interpreter is guaranteed to exist on a deployed box; bare python3
# is not (and on Windows it is a Store stub that prints an advert).
PY_BIN="$VENV/bin/python"
[[ -x "$PY_BIN" ]] || PY_BIN="$VENV/Scripts/python.exe"
[[ -x "$PY_BIN" ]] || PY_BIN="$(command -v python3 || command -v python)"

say()  { printf "%-34s %s\n" "$1" "$2"; }
bad()  { printf "%-34s %s\n" "$1" "FAIL: $2"; fail=1; }

echo "=== football forecasts healthcheck $(date -Is) ==="

# 1. The three files exist and are valid JSON.
for f in predictions.json track-record.json meta.json; do
  p="$FORECAST_OUT/$f"
  if [[ ! -f "$p" ]]; then
    bad "$f" "missing at $p"
  elif ! "$PY_BIN" -c "import json,sys; json.load(open(sys.argv[1],encoding='utf-8'))" "$p" 2>/dev/null; then
    bad "$f" "not valid JSON"
  else
    say "$f" "ok ($(du -h "$p" | cut -f1))"
  fi
done

# 2. No leftover temp files. One means a publish died mid-write.
if compgen -G "$FORECAST_OUT/*.tmp" > /dev/null; then
  bad "temp files" "a publish did not finish: $(ls "$FORECAST_OUT"/*.tmp)"
else
  say "temp files" "none"
fi

# 3. How fresh is the publish? This is the check that catches silent stalls.
if [[ -f "$FORECAST_OUT/meta.json" ]]; then
  # The limit comparison happens in Python, not bc, which is not installed
  # everywhere. It prints the age and exits 1 when that age is over the limit.
  if age_h=$(MAX_AGE_HOURS="$MAX_AGE_HOURS" "$PY_BIN" - "$FORECAST_OUT/meta.json" <<'PY'
import json, os, sys
from datetime import datetime, timezone
m = json.load(open(sys.argv[1], encoding="utf-8"))
t = datetime.fromisoformat(m["published_at"])
age = (datetime.now(timezone.utc) - t).total_seconds() / 3600
print(f"{age:.1f}")
sys.exit(1 if age > float(os.environ["MAX_AGE_HOURS"]) else 0)
PY
  ); then
    say "publish freshness" "${age_h}h ago"
  else
    bad "publish freshness" "last publish was ${age_h}h ago (limit ${MAX_AGE_HOURS}h)"
  fi
fi

# 4. What is actually in the store.
if [[ -f "$FORECAST_DB" ]]; then
  counts=$("$PY_BIN" - "$FORECAST_DB" <<'PY'
import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
p = c.execute("select count(*) from predictions").fetchone()[0]
s = c.execute("select count(*) from predictions where was_correct is not null").fetchone()[0]
u = c.execute("select count(*) from predictions where was_correct is null and date >= date('now')").fetchone()[0]
r = c.execute("select count(*) from team_ratings").fetchone()[0]
print(f"{p} forecasts, {s} settled, {u} upcoming, {r} ratings")
PY
)
  say "store" "$counts"
else
  bad "store" "no database at $FORECAST_DB"
fi

# 5. Did the last run of each job finish cleanly?
for job in run settle; do
  log="$LOG_DIR/$job.log"
  if [[ ! -f "$log" ]]; then
    bad "$job log" "never run"
  else
    last=$(grep -E "finished ok|starting" "$log" | tail -1)
    if [[ "$last" == *"finished ok"* ]]; then
      say "$job log" "last finished ok"
    else
      bad "$job log" "last entry is a start with no finish - it crashed or is stuck"
    fi
  fi
done

# 6. Is the site actually serving the data?
if [[ -n "${PUBLIC_URL:-}" ]]; then
  code=$(curl -s -o /dev/null -w '%{http_code}' "$PUBLIC_URL/data/meta.json" || echo 000)
  [[ "$code" == "200" ]] && say "public meta.json" "HTTP 200" || bad "public meta.json" "HTTP $code"
fi

echo
[[ $fail -eq 0 ]] && echo "ALL OK" || echo "PROBLEMS FOUND"
exit $fail
