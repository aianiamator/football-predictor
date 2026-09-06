"""Rebuild the committed history snapshot.

Completed seasons never change, but the engine was re-downloading eight years
of them on every run - 56 files, five times a day, from a free site one person
maintains. That is almost certainly what got the CI runner blocked, and it is
wasteful regardless.

This writes those finished seasons to data/history.csv.gz, which IS committed.
The engine then reads them from disk and only asks the network for the season
currently in progress: 7 requests per run instead of 56.

Re-run this when a new season finishes, or if the source publishes corrections
to a past season:

    python -m scripts.build_history
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from engine import data as dataio

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "history.csv.gz"

# Every season the engine can ask for, minus the one still being played.
N_SEASONS = 10


def main() -> int:
    codes = dataio.season_codes(N_SEASONS)
    finished, current = codes[:-1], codes[-1]
    print(f"finished seasons : {', '.join(finished)}")
    print(f"current (skipped): {current}\n")

    frames = []
    for league in dataio.LEAGUES:
        got = []
        for season in finished:
            raw = dataio._fetch(
                f"{dataio.BASE}/{season}/{league}.csv",
                dataio.CACHE / season / f"{league}.csv",
                max_age_hours=None,          # finished seasons: cache forever
            )
            if not raw:
                continue
            parsed = dataio._parse(raw, league, season)
            if not parsed.empty:
                frames.append(parsed)
                got.append(season)
        if got:
            print(f"  {league:4s} {len(got)} seasons")

    if not frames:
        print("\nNothing collected - the source is unreachable and the cache is empty.")
        return 1

    hist = pd.concat(frames, ignore_index=True).sort_values(
        ["league", "date"]).reset_index(drop=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    hist.to_csv(OUT, index=False, compression="gzip")
    size_mb = OUT.stat().st_size / 1e6

    print(f"\nwrote {OUT.relative_to(ROOT)}")
    print(f"  {len(hist):,} matches, {hist['league'].nunique()} leagues, "
          f"{hist['date'].min().date()} to {hist['date'].max().date()}")
    print(f"  {size_mb:.2f} MB on disk")
    return 0


if __name__ == "__main__":
    sys.exit(main())
