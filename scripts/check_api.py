"""Check the API token and build the team-name mapping.

This is the step that decides whether switching sources is safe. Every stored
forecast is keyed by a football-data.co.uk team name; results arriving from the
API carry that club's name in a different form. A name that fails to map leaves
a forecast stuck 'awaiting a result' forever, and a name mapped to the WRONG
club settles it against a different match - which would quietly corrupt the
public track record.

So this script proposes a mapping, then reports exactly what it could not
resolve. Nothing is accepted automatically on a near-miss.

    python -m scripts.check_api          # report only
    python -m scripts.check_api --write  # write data/team_aliases.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from engine import api_source as api
from engine import data as dataio

ROOT = Path(__file__).resolve().parent.parent


def current_squad_names(league: str) -> set[str]:
    """Team names as our own history spells them, current season only.

    Older seasons contain relegated clubs that are not in this season's league,
    and matching against those adds ways to be wrong for no benefit.
    """
    df = dataio.load_league(league, n_seasons=3)
    if df.empty:
        return set()
    latest = df[df["date"] >= df["date"].max() - __import__("pandas").Timedelta(days=400)]
    return set(latest["home_team"]) | set(latest["away_team"])


def main(write: bool = False) -> int:
    try:
        api.token()
    except api.ApiUnavailable as exc:
        print(f"TOKEN MISSING\n  {exc}")
        return 2

    mapping: dict[str, str] = {}
    unresolved: list[tuple[str, str, list[str]]] = []
    total = 0

    for league, comp in api.COMPETITIONS.items():
        ours = current_squad_names(league)
        by_key = {api.normalise(n): n for n in ours}
        try:
            teams = api._get(f"competitions/{comp}/teams")["teams"]
        except api.ApiUnavailable as exc:
            print(f"  {league}: could not list teams - {exc}")
            return 1

        hit = 0
        for t in teams:
            total += 1
            # Try the API's several spellings of the same club.
            for candidate in (t.get("name"), t.get("shortName"), t.get("tla")):
                if not candidate:
                    continue
                ours_name = by_key.get(api.normalise(candidate))
                if ours_name:
                    mapping[t["name"]] = ours_name
                    hit += 1
                    break
            else:
                near = sorted(ours, key=lambda o: -_overlap(
                    api.normalise(t["name"]), api.normalise(o)))[:3]
                unresolved.append((league, t["name"], near))
        print(f"  {league} ({comp}): {hit}/{len(teams)} teams mapped")

    print(f"\n{len(mapping)}/{total} names resolved automatically")

    if unresolved:
        print(f"\n{len(unresolved)} NEED A DECISION - nothing was guessed:")
        for league, name, near in unresolved:
            print(f"  {league}  {name!r}")
            print(f"        closest in our data: {', '.join(repr(n) for n in near)}")
        print("\nAdd each to data/team_aliases.json as \"API name\": \"our name\".")

    if write:
        out = ROOT / "data" / "team_aliases.json"
        existing = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
        # Hand-confirmed entries win. The automatic pass exists to save typing,
        # not to overrule a decision someone has already checked - and the
        # near-misses above show why: it offered 'Villarreal' for Atletico
        # Madrid and 'Sp Braga' for Benfica.
        merged = {**mapping, **existing}
        out.write_text(json.dumps(dict(sorted(merged.items())), indent=2,
                                  ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\nwrote {out.relative_to(ROOT)} ({len(merged)} names)")

    return 1 if unresolved else 0


def _overlap(a: str, b: str) -> int:
    """Crude similarity, only ever used to suggest candidates to a human."""
    return sum(1 for i in range(min(len(a), len(b))) if a[i] == b[i])


if __name__ == "__main__":
    sys.exit(main(write="--write" in sys.argv))
