"""Fill in real results on past forecasts.

This is what makes the public track record real, so it is deliberately narrow:

  * it only ever writes results for matches that have actually finished
  * it never touches a stored forecast - not the percentages, not the wording
  * a match already settled is skipped, so re-running is safe

The forecast columns are additionally protected by a trigger in schema.sql,
which aborts any update that would alter a settled forecast even if it came
from outside this module.

Run:  python -m engine.settle
"""
from __future__ import annotations

import sys

import pandas as pd

from . import data as dataio
from . import store
from .run import OUT

# A finished match must be at least this old before we trust the feed's row for
# it. football-data publishes results promptly, but a fixture postponed at short
# notice can briefly appear with placeholder values.
MIN_AGE_HOURS = 3


def settle(leagues: list[str] | None = None, n_seasons: int = 2,
           publish: bool = True, db=None, out=None) -> dict:
    leagues = leagues or dataio.CORE_LEAGUES
    out = out or OUT
    conn = store.connect(db)
    try:
        pending = conn.execute(
            "select id, league_code, date, home_team, away_team "
            "from predictions where fixture_status = 'pending' order by date"
        ).fetchall()

        if not pending:
            print("Nothing awaiting a result.")
            if publish:
                print("Published:", store.publish_json(conn, out))
            return {"settled": 0, "pending": 0, "not_found": 0}

        print(f"{len(pending)} forecast(s) awaiting a result.")

        # Recent seasons only: nothing older can still be unsettled in practice.
        results = dataio.load_many(leagues, n_seasons=n_seasons)
        if results.empty:
            print("No results available; leaving everything as it is.")
            return {"settled": 0, "pending": len(pending), "not_found": 0}

        cutoff = pd.Timestamp.now() - pd.Timedelta(hours=MIN_AGE_HOURS)
        results = results[results["date"] <= cutoff]

        # Index by the same key the store uses.
        played = {
            (r.league, str(pd.Timestamp(r.date).date()), r.home_team, r.away_team):
                (int(r.home_goals), int(r.away_goals))
            for r in results.itertuples()
        }

        settled = not_found = 0
        for row in pending:
            key = (row["league_code"], row["date"], row["home_team"], row["away_team"])
            score = played.get(key)
            if score is None:
                not_found += 1
                continue
            if store.settle(conn, *key, score[0], score[1]):
                settled += 1

        still_pending = len(pending) - settled
        print(f"Settled {settled}. Still pending {still_pending} "
              f"(of which {not_found} not yet in the results feed).")

        if settled:
            acc = conn.execute(
                "select count(*) n, sum(case when was_correct=1 then 1 else 0 end) hits "
                "from predictions where fixture_status='finished' "
                "and was_correct is not null").fetchone()
            if acc["n"]:
                print(f"Track record now {acc['hits']}/{acc['n']} "
                      f"({100.0 * acc['hits'] / acc['n']:.1f}%)")

        if publish:
            published = store.publish_json(conn, out)
            print(f"Published: {published['upcoming']} upcoming, "
                  f"{published['settled']} settled")

        return {"settled": settled, "pending": still_pending, "not_found": not_found}
    finally:
        conn.close()


if __name__ == "__main__":
    settle()
    sys.exit(0)
