"""Structural checks on the team-name mapping.

The mapping is the join between two sources that name the same clubs
differently. It is the one place where a silent error corrupts the public
track record rather than merely breaking a run: a name pointed at the wrong
club settles a forecast against a different match, and nothing on screen would
look wrong.

These checks run offline, with no token, so they guard every commit. The live
check against the API - does every club in every league resolve? - lives in
scripts/check_api.py, which needs a token.

Run with:  python -m tests.test_aliases
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ALIASES = ROOT / "data" / "team_aliases.json"
HISTORY = ROOT / "data" / "history.csv.gz"

# Clubs that are genuinely new to a league we cover, so they appear in the
# current season but not in the nine finished seasons of the snapshot. Adding
# one here should be a deliberate act: it is the moment to check the spelling
# against the live data rather than wave it through.
NEWLY_PROMOTED = {
    "Academico Viseu",     # promoted to the Primeira Liga for 2026/27
}


def _aliases() -> dict[str, str]:
    return json.loads(ALIASES.read_text(encoding="utf-8"))


def test_file_is_well_formed():
    table = _aliases()
    assert table, "the alias table is empty"
    blank = [k for k, v in table.items() if not str(v).strip()]
    assert not blank, f"aliases with no target: {blank}"
    assert len(table) >= 100, f"only {len(table)} aliases; a league is missing"
    print(f"  {len(table)} aliases, none blank")
    return True


def test_no_two_clubs_share_a_target():
    """The error that would corrupt the track record silently."""
    table = _aliases()
    dupes = {v: [k for k in table if table[k] == v]
             for v, n in Counter(table.values()).items() if n > 1}
    for target, sources in dupes.items():
        print(f"  COLLISION: {sources} all map to {target!r}")
    assert not dupes, (
        "two API clubs map to the same stored name; one of them would settle "
        "against the other's result")
    print(f"  {len(set(table.values()))} distinct targets, no collisions")
    return True


def test_targets_are_real_team_names():
    """Catch a typo in a hand-added mapping.

    A misspelled target never matches anything, so the forecast stays
    'awaiting a result' for ever and no error is ever raised.
    """
    table = _aliases()
    hist = pd.read_csv(HISTORY, compression="gzip", usecols=["home_team", "away_team"])
    known = set(hist["home_team"]) | set(hist["away_team"]) | NEWLY_PROMOTED

    unknown = sorted({v for v in table.values() if v not in known})
    for u in unknown:
        print(f"  UNKNOWN TARGET: {u!r}")
    assert not unknown, (
        "these targets match no team in nine seasons of history. Either the "
        "spelling is wrong, or the club is newly promoted - in which case add "
        "it to NEWLY_PROMOTED after checking it against the live season.")
    print(f"  all {len(set(table.values()))} targets are real team names")
    return True


def main():
    tests = [
        ("alias file is well formed", test_file_is_well_formed),
        ("no two clubs share a target", test_no_two_clubs_share_a_target),
        ("every target is a real team", test_targets_are_real_team_names),
    ]
    failed = 0
    for name, fn in tests:
        print(f"\n[ {name} ]")
        try:
            fn()
            print("  PASS")
        except AssertionError as exc:
            print(f"  FAIL: {exc}")
            failed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR: {type(exc).__name__}: {exc}")
            failed += 1
    print(f"\n{'ALL PASSED' if failed == 0 else str(failed) + ' FAILED'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
