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
        dataio.reset_fetch_failures()
        results = dataio.load_many(leagues, n_seasons=n_seasons)
        if results.empty:
            print("No results available; leaving everything as it is.")
            return {"settled": 0, "pending": len(pending), "not_found": 0}

        # Add the API's results. Cross-checked over 45 days on 165 matches
        # both sources carried: every scoreline agreed, and the API also had
        # 37 finished matches the CSV feed had not published. So it is added
        # as an equal source rather than a last resort, and either one alone
        # is enough to settle.
        api_rows = 0
        try:
            from engine import api_source
            extra = api_source.results(leagues=[l for l in leagues
                                                if l in api_source.COMPETITIONS])
            if not extra.empty:
                cols = ["league", "date", "home_team", "away_team",
                        "home_goals", "away_goals"]
                results = pd.concat([results[cols], extra[cols]], ignore_index=True)
                results = results.drop_duplicates(
                    subset=["league", "date", "home_team", "away_team"], keep="first")
                api_rows = len(extra)
                print(f"  results: +{api_rows} from api.football-data.org")
        except Exception as exc:                   # noqa: BLE001
            print(f"  API results unavailable ({type(exc).__name__}); "
                  f"using football-data.co.uk only")

        # Finished seasons now come from the committed snapshot, so `results`
        # is never empty. That would let a blocked feed settle nothing and
        # still finish green, which is worse than failing outright: a result
        # that arrived today exists only in a live source. Stop only when
        # BOTH have failed - one working source is enough.
        blocked = dataio.fetch_failures()
        if api_rows == 0 and len(blocked) >= len(leagues):
            detail = "".join(f"\n    {u}" for u in blocked[:4])
            raise SystemExit(
                "\n" + "=" * 68
                + "\nRESULTS FEED UNAVAILABLE - nothing was settled\n"
                + "=" * 68
                + f"\n  {len(blocked)} of {len(leagues)} leagues could not be refreshed:"
                + detail
                + f"\n\n  {len(pending)} forecast(s) stay marked 'awaiting a result',"
                "\n  which is exactly what they are. Nothing was scored against"
                "\n  stale data and no forecast was altered. The next run retries.\n"
            )

        cutoff = pd.Timestamp.now() - pd.Timedelta(hours=MIN_AGE_HOURS)
        results = results[results["date"] <= cutoff]

        # Index by the same key the store uses.
        played = {
            (r.league, str(pd.Timestamp(r.date).date()), r.home_team, r.away_team):
                (int(r.home_goals), int(r.away_goals))
            for r in results.itertuples()
        }

        settled = not_found = shifted = 0
        for row in pending:
            key = (row["league_code"], row["date"], row["home_team"], row["away_team"])
            score = played.get(key)
            if score is None:
                # The two sources date a match from different time zones, so a
                # late kick-off can land either side of midnight. Accept a
                # one-day shift for the SAME two clubs in the same league -
                # they never meet on consecutive days, so this cannot pull in
                # a different fixture. Without it such a forecast would stay
                # 'awaiting a result' for ever.
                for delta in (-1, 1):
                    near = (key[0],
                            str((pd.Timestamp(row["date"]) + pd.Timedelta(days=delta)).date()),
                            key[2], key[3])
                    if near in played:
                        score = played[near]
                        shifted += 1
                        break
            if score is None:
                not_found += 1
                continue
            if store.settle(conn, *key, score[0], score[1]):
                settled += 1

        still_pending = len(pending) - settled
        print(f"Settled {settled}. Still pending {still_pending} "
              f"(of which {not_found} not yet in the results feed).")
        if shifted:
            print(f"  {shifted} matched a day either side (time-zone edge).")

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
