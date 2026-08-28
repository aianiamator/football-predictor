#!/usr/bin/env bash
#
# Build the app and put it where nginx serves it.
#
# The app and the published JSON share an origin, so the app fetches /data/...
# relative to itself. No CORS, no second hostname, no VITE_DATA_URL to forget.
#
source "$(dirname "$0")/env.sh"

cd "$APP_DIR"

echo "== python deps =="
"$VENV/bin/pip" install -q -r requirements.txt

echo "== build app =="
npm ci --prefix app
npm run build --prefix app

echo "== publish =="
# --delete keeps the web root clean, but data/ is EXCLUDED because the engine
# owns it. Without that exclusion a deploy would wipe every forecast.
rsync -a --delete --exclude 'data/' app/dist/ "$WEB_ROOT/"
mkdir -p "$FORECAST_OUT"

echo "== first run =="
"$VENV/bin/python" -m engine.run

echo "== done =="
"$(dirname "$0")/healthcheck.sh"
