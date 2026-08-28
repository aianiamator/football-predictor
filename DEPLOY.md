# Deployment

## Current state (2026-08-28)

**Live at https://football-predictor.aianimatorhub.workers.dev**

Running on GitHub Actions + Cloudflare Workers. No server to maintain.

    football-data.co.uk -> GitHub Actions (cron) -> commits to repo
                        -> Cloudflare Workers static assets -> app

- `.github/workflows/forecasts.yml` runs the engine: forecasts at 05:30 UTC
  daily, results every 6 hours. It runs the leakage audit BEFORE publishing, so
  a run that would leak future information fails instead of shipping.
- Cloudflare redeploys automatically on every push to `main`.
- `app/wrangler.toml` declares the assets directory. It is a **Worker**, not a
  Pages project - `pages_build_output_dir` is silently ignored here, which once
  caused the source `index.html` to be published instead of the built one.
- First visit costs ~23 KB. Repeat visits ~5 KB.

### The custom domain, deferred deliberately

`forecasts.future-intelligence.net` is NOT connected. Cloudflare Workers custom
domains require the zone to be hosted on Cloudflare, and `future-intelligence.net`
has its DNS at Name.com pointing at a live Replit site with a Stripe paywall.

**Decision: stay on the workers.dev address rather than migrate a live revenue
site's nameservers to add a football subdomain.** The app works; the URL is
cosmetic.

When it is worth doing, the low-risk route is a **Pages project plus a CNAME**,
which leaves DNS at Name.com untouched:

1. Change `app/wrangler.toml` from `[assets] directory` to
   `pages_build_output_dir = "./dist"` (Pages format, not Workers format).
2. Create a Pages project from the same repo: root directory `app`,
   build command `npm ci && npm run build:site`.
3. Pages -> Custom domains -> add `forecasts.future-intelligence.net`; it gives
   a CNAME target.
4. At Name.com add one CNAME: host `forecasts`, value = that target.
5. Delete the old Worker.

DNS snapshot taken 2026-08-28, which must still hold afterwards:

| Record | Value |
|---|---|
| A | `34.111.179.208` (Replit, the FISL site) |
| TXT | `replit-verify=720023b5-e805-4a64-8b04-7d93e9666ff6` |
| MX | none - no email on this domain, so nothing to break |
| NS | `ns1cny` / `ns2ckr` / `ns3jkl` / `ns4hny.name.com` |

---

# Alternative: deploying to a Hetzner box

The whole system is one directory, one SQLite file, and three JSON files served
as static assets. There is no application server, no database server, no API,
and no key anywhere in the frontend.

```
football-data.co.uk → engine (cron) → SQLite → static JSON → nginx → Cloudflare → app
```

## 1. Put the code on the box

```bash
sudo mkdir -p /srv/football-predictor && sudo chown "$USER" /srv/football-predictor
git clone <your-repo> /srv/football-predictor
cd /srv/football-predictor

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Node 20+ for the app build
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs rsync
```

## 2. Prove it works before scheduling anything

```bash
.venv/bin/python -m tests.test_model
.venv/bin/python -m tests.test_leakage
.venv/bin/python -m tests.test_store
.venv/bin/python -m tests.test_settle
.venv/bin/python -m tests.test_payload
```

All five must pass. `test_leakage` is the one that matters most — it fails the
build if accuracy ever exceeds 60%, which would mean future information is
leaking into training.

## 3. Web root and nginx

The app and its data share an origin, so the app fetches `/data/...` relative to
itself. No CORS, no second hostname, no `VITE_DATA_URL` to forget.

```bash
sudo mkdir -p /var/www/forecasts/data
sudo chown -R "$USER" /var/www/forecasts
```

`/etc/nginx/sites-available/forecasts`:

```nginx
server {
  listen 80;
  server_name forecasts.example.com;
  root /var/www/forecasts;
  index index.html;

  gzip on;
  gzip_types text/css application/javascript application/json image/svg+xml;
  gzip_min_length 256;

  # Hashed filenames, so these can be cached forever.
  location /assets/ {
    expires 1y;
    add_header Cache-Control "public, immutable";
  }

  # Forecasts change weekly. Short cache, and Cloudflare revalidates.
  location /data/ {
    expires 10m;
    add_header Cache-Control "public, max-age=600, stale-while-revalidate=86400";
  }

  # Never cache the shell or the worker, or an update can never reach anyone.
  location = /index.html { add_header Cache-Control "no-cache"; }
  location = /sw.js      { add_header Cache-Control "no-cache"; }

  location / { try_files $uri $uri/ /index.html; }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/forecasts /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d forecasts.example.com
```

## 4. Deploy

```bash
./scripts/deploy.sh
```

Builds the app, rsyncs it to the web root, runs the engine once, and finishes
with a healthcheck. The rsync deliberately **excludes `data/`** — the engine owns
that directory, and without the exclusion a deploy would wipe every forecast.

The build refuses to run while `app/public/data/` exists. That directory holds
development data with invented fixtures, and shipping it would present made-up
matches as real forecasts.

## 5. Cron

```bash
crontab -e
```

```cron
# Forecasts. Daily is right even though the round is weekly: fixtures appear in
# the feed a few days ahead, and a stored forecast is refreshed until its match
# is played.
30 5 * * * /srv/football-predictor/scripts/run_predictions.sh

# Results. More often than the forecasts, because this is what makes the public
# track record real. Matches finish through the evening across time zones.
0 */6 * * * /srv/football-predictor/scripts/run_settle.sh

# Tell me when it has quietly stopped.
0 9 * * * /srv/football-predictor/scripts/healthcheck.sh || echo "forecasts healthcheck failed"
```

Both job scripts take a `flock`, so a slow run can never be overtaken by the
next one and corrupt the database.

Times are the server's zone. `sudo timedatectl set-timezone UTC` if you want
them predictable.

## 6. Cloudflare

Point the DNS record at the box with the orange cloud on. Then the part people
miss:

> **Cloudflare does not cache `.json` by default.** Without a rule, every visit
> hits your server and you will conclude the CDN is broken.

Create a **Cache Rule**:

- **If** URI Path starts with `/data/`
- **Then** Eligible for cache, Edge TTL 10 minutes, Browser TTL respect origin

And purge that path after each run if you want changes visible immediately.
Otherwise a forecast can be up to 10 minutes stale, which is fine for a weekly
product.

## Running it from n8n instead

If you would rather see the runs in n8n than in cron, import
`scripts/n8n-workflow.json` and set `APP_DIR`. It is two Schedule triggers into
two Execute Command nodes, with the healthcheck on a failure branch.

The scripts are the same ones cron calls, so nothing else changes. **Use one or
the other, not both** — the `flock` will stop them colliding, but you will spend
an afternoon wondering why half your runs say "skipping".

n8n needs shell access to the box. If it runs in Docker, mount the project and
the venv, or switch the Execute Command nodes to SSH nodes.

## Confirming it is actually running

```bash
./scripts/healthcheck.sh
```

```
=== football forecasts healthcheck ===
predictions.json                   ok (24K)
track-record.json                  ok (4.9K)
meta.json                          ok (4.0K)
temp files                         none
publish freshness                  6.2h ago
store                              412 forecasts, 380 settled, 32 upcoming, 203 ratings
run log                            last finished ok
settle log                         last finished ok
ALL OK
```

Exits non-zero on any problem, so it works as a monitoring probe unchanged.
Set `PUBLIC_URL=https://forecasts.example.com` to also check the live site.

### What to look at, in order

| Symptom | Check |
|---|---|
| Site shows nothing | `curl -I https://your-site/data/predictions.json` |
| Forecasts look stale | `publish freshness` in the healthcheck |
| Nothing settling | `tail -50 logs/settle.log` |
| Job seems stuck | `ls -la /tmp/football-*.lock`, then `pgrep -af engine` |
| Everything "fine" but empty | `.venv/bin/python -c "from engine import data; print(len(data.load_fixtures()))"` |

That last one is the important one. **Zero upcoming forecasts is usually not a
fault.** football-data publishes fixtures only a few days before each round, so
between rounds the feed is legitimately empty and the engine correctly refuses
to forecast matches that have already kicked off. Check the feed before
debugging the engine.

### The failure that will not announce itself

The jobs exit 0, publish nothing, and the site keeps serving last week's
forecasts looking entirely normal. That is exactly what `publish freshness` in
the healthcheck exists to catch, and why the daily cron entry above pipes its
failure somewhere you will see it.

## Backups

The SQLite file is the only thing that cannot be regenerated — it holds the
forecasts as they were published, which is what makes the track record
trustworthy. Everything else can be rebuilt from the public CSV feed.

```cron
15 3 * * * sqlite3 /srv/football-predictor/data/forecasts.db ".backup '/srv/backups/forecasts-$(date +\%u).db'"
```

Seven rotating daily copies. Use `.backup`, not `cp` — the database is in WAL
mode and a plain copy can catch it mid-write.
