"""DEVELOPMENT DATA ONLY. Never run this against the production store.

football-data's fixtures feed is empty between rounds, so there is nothing to
build the app against out of season. This writes a realistic dataset into
app/public/data/ so the interface can be developed and verified.

What is real here:
  * the teams, and every forecast, which is genuine model output
  * the settled results, which are real historical scorelines

What is NOT real:
  * the upcoming fixture list, which is constructed - the real feed decides this
  * the track record, which is produced by forecasting recent matches from data
    that predates them. That is a legitimate out-of-sample exercise, but it is
    NOT a record of forecasts published in advance, and must never be presented
    to users as one.

Run:  python -m tools.dev_seed
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from engine import data as dataio
from engine import store
from engine.model import fit
from engine.run import build_fixture_payload

ROOT = Path(__file__).resolve().parent.parent
DEV_DB = ROOT / "data" / "dev_forecasts.db"
DEV_OUT = ROOT / "app" / "public" / "data"

LEAGUES = ["E0", "SP1", "I1", "D1", "P1"]
SETTLED_WINDOW_DAYS = 45
UPCOMING_DAYS = 6


def main() -> int:
    DEV_DB.unlink(missing_ok=True)
    for suffix in ("-wal", "-shm"):
        DEV_DB.with_name(DEV_DB.name + suffix).unlink(missing_ok=True)

    conn = store.connect(DEV_DB)
    total_up = total_settled = 0

    for code in LEAGUES:
        hist = dataio.load_league(code, n_seasons=4)
        if hist.empty:
            print(f"  {code}: no data, skipping")
            continue

        last = hist["date"].max()
        cutoff = last - pd.Timedelta(days=SETTLED_WINDOW_DAYS)

        # --- track record: forecast recent matches using only earlier data ---
        train = hist[hist["date"] < cutoff]
        recent = hist[hist["date"] >= cutoff]
        if len(train) < 200 or recent.empty:
            continue
        model = fit(train, league=code, reference_date=cutoff)

        settled_rows = []
        for r in recent.itertuples():
            if not (model.knows(r.home_team) and model.knows(r.away_team)):
                continue
            payload = build_fixture_payload(
                model.predict(r.home_team, r.away_team), code, r.date, "15:00")
            settled_rows.append((payload, int(r.home_goals), int(r.away_goals)))

        store.upsert_predictions(conn, [p for p, _, _ in settled_rows])
        for payload, hg, ag in settled_rows:
            if store.settle(conn, code, payload["date"], payload["home_team"],
                            payload["away_team"], hg, ag):
                total_settled += 1

        # --- upcoming: constructed fixtures from the most recent squads ------
        full = fit(hist, league=code)
        squad = sorted(
            pd.concat([recent["home_team"], recent["away_team"]]).value_counts().head(12).index
        )
        today = pd.Timestamp.now().normalize()
        upcoming = []
        for i in range(0, len(squad) - 1, 2):
            home, away = squad[i], squad[i + 1]
            if not (full.knows(home) and full.knows(away)):
                continue
            day = today + pd.Timedelta(days=1 + (i // 2) % UPCOMING_DAYS)
            kick = ["15:00", "17:30", "20:00"][(i // 2) % 3]
            upcoming.append(build_fixture_payload(full.predict(home, away), code, day, kick))

        store.upsert_predictions(conn, upcoming)
        total_up += len(upcoming)
        print(f"  {code}: {len(upcoming)} upcoming, {len(settled_rows)} settled")

    published = store.publish_json(conn, DEV_OUT)
    conn.close()

    print(f"\nDEV DATA (not for publication)")
    print(f"  {total_up} upcoming, {total_settled} settled")
    print(f"  written to {DEV_OUT}")
    for name in ("predictions.json", "track-record.json", "meta.json"):
        print(f"    {name:<20}{(DEV_OUT / name).stat().st_size / 1024:7.1f} KB")
    print(f"  store: {DEV_DB}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
