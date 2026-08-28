#!/usr/bin/env bash
# Shared settings for the scheduled jobs. Edit paths here, nowhere else.
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/srv/football-predictor}"
VENV="${VENV:-$APP_DIR/.venv}"
WEB_ROOT="${WEB_ROOT:-/var/www/forecasts}"

# The engine writes published JSON straight into the directory nginx serves.
# No copy step means no copy step that can silently fail and leave the site
# showing last week's forecasts.
export FORECAST_OUT="${FORECAST_OUT:-$WEB_ROOT/data}"
export FORECAST_DB="${FORECAST_DB:-$APP_DIR/data/forecasts.db}"

LOG_DIR="${LOG_DIR:-$APP_DIR/logs}"
LOCK_DIR="${LOCK_DIR:-/tmp}"

mkdir -p "$LOG_DIR" "$FORECAST_OUT" "$(dirname "$FORECAST_DB")"
