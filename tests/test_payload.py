"""Payload shape and product-constraint checks for the published output.

The engine writes into SQLite and publishes derived static JSON, which the app
reads with no interpretation layer. So the payload is the contract, and the
non-negotiable copy rules have to be enforced here rather than trusted to
review.

Checks:
  1. every payload key maps to a column in schema.sql
  2. the three-way percentages are whole numbers that sum to ~100
  3. both_teams_score is NOT published (no measurable edge in backtesting)
  4. over_2_5_pct is published only for leagues that cleared the edge bar
  5. no banned word appears in any user-facing string
  6. no summary states a bare single-outcome verdict
  7. confidence bands match the thresholds set from observed calibration

Run with:  python -m tests.test_payload
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

from engine import data as dataio
from engine.model import fit
from engine.run import OVER_UNDER_LEAGUES, build_fixture_payload, confidence_band, plain_summary

ROOT = Path(__file__).resolve().parent.parent

# Never in the interface or copy, in any form.
BANNED = ["bet", "betting", "odds", "stake", "tip", "accumulator",
          "banker", "sure", "guaranteed"]

# Anything implying certainty. "strong favourite" is the ceiling.
OVERCLAIM = ["will win", "certain", "definitely", "guaranteed", "lock",
             "cannot lose", "can't lose", "no chance"]


def _banned_hits(text: str) -> list[str]:
    """Whole-word matches only, so 'ensure' and 'measure' do not false-positive."""
    low = text.lower()
    return [w for w in BANNED if re.search(rf"\b{re.escape(w)}\b", low)]


def _sample_payloads(n_seasons: int = 4):
    """Real model output for constructed fixtures.

    football-data's fixtures feed is empty out of season, so the fixture list
    is constructed here. The ratings and forecasts are genuine model output.
    """
    out = []
    tomorrow = pd.Timestamp.now().normalize() + pd.Timedelta(days=1)
    for code in ["E0", "SP1", "I1"]:
        history = dataio.load_league(code, n_seasons=n_seasons)
        if history.empty:
            continue
        model = fit(history, league=code)
        recent = history[history["date"] >= history["date"].max() - pd.Timedelta(days=120)]
        pairs = list(dict.fromkeys(zip(recent["home_team"], recent["away_team"])))[:4]
        for home, away in pairs:
            if not (model.knows(home) and model.knows(away)):
                continue
            pred = model.predict(home, away)
            out.append(build_fixture_payload(pred, code, tomorrow, "20:00"))
    return out


def _schema_columns() -> set[str]:
    sql = (ROOT / "schema.sql").read_text(encoding="utf-8")
    block = sql[sql.index("create table if not exists predictions"):]
    block = block[: block.index("\n);")]
    cols = set()
    for line in block.splitlines()[1:]:
        line = line.strip()
        if not line or line.startswith("--") or line.startswith("unique"):
            continue
        cols.add(line.split()[0])
    return cols


def test_schema_match():
    payloads = _sample_payloads()
    assert payloads, "no payloads produced"
    cols = _schema_columns()
    keys = set(payloads[0])
    extra = keys - cols
    print(f"  {len(payloads)} payloads, {len(keys)} keys, {len(cols)} schema columns")
    assert not extra, f"payload keys with no column in schema.sql: {sorted(extra)}"
    return True


def test_percentages():
    for p in _sample_payloads():
        total = p["home_win_pct"] + p["draw_pct"] + p["away_win_pct"]
        assert all(isinstance(p[k], int) for k in ("home_win_pct", "draw_pct", "away_win_pct")), \
            "percentages must be pre-rounded ints so the UI never does maths"
        assert 99 <= total <= 101, f"three-way percentages sum to {total}"
    print("  all three-way splits are whole numbers summing to 99-101")
    return True


def test_btts_not_published():
    for p in _sample_payloads():
        for key in p:
            assert "both" not in key and "btts" not in key, \
                f"both-teams-score must not be published, found key {key!r}"
    print("  both_teams_score absent from every payload")
    return True


def test_over_under_gating():
    seen = {}
    for p in _sample_payloads():
        code = p["league_code"]
        seen[code] = p["over_2_5_pct"]
        if code in OVER_UNDER_LEAGUES:
            assert p["over_2_5_pct"] is not None, f"{code} should publish over/under"
        else:
            assert p["over_2_5_pct"] is None, \
                f"{code} has no measured over/under edge but published {p['over_2_5_pct']}"
    print(f"  over/under gating correct: {seen}")
    return True


def test_no_banned_words():
    fields = ["summary", "confidence", "league", "country", "likely_score"]
    for p in _sample_payloads():
        for f in fields:
            val = str(p.get(f, ""))
            hits = _banned_hits(val)
            assert not hits, f"banned word {hits} in {f}: {val!r}"
    print(f"  no banned words in any of {fields}")
    return True


def test_no_certainty_claims():
    samples = []
    for p in _sample_payloads():
        s = p["summary"].lower()
        samples.append(p["summary"])
        for phrase in OVERCLAIM:
            assert phrase not in s, f"summary implies certainty: {p['summary']!r}"
        # Every favourite sentence must carry the draw or the upset alongside it,
        # because a draw is almost never the model's argmax but happens ~25%.
        if "favourite" in s or "more likely" in s:
            assert ("draw" in s or "close" in s), \
                f"single-outcome verdict with no counterweight: {p['summary']!r}"
    print(f"  {len(samples)} summaries clean. Examples:")
    for s in samples[:3]:
        print(f"    - {s}")
    return True


def test_confidence_bands():
    cases = [(0.95, "strong", 3), (0.70, "strong", 3), (0.699, "moderate", 2),
             (0.52, "moderate", 2), (0.519, "close", 1), (0.34, "close", 1)]
    for p, band, stars in cases:
        b, s, colour = confidence_band(p)
        assert (b, s) == (band, stars), f"{p} gave {b}/{s}, expected {band}/{stars}"
        assert colour.startswith("#")
    print("  bands: strong >=0.70, moderate >=0.52, close below")
    return True


def test_summary_draw_case():
    """A draw-favoured fixture must not name a winner."""
    pred = {"home_team": "Alpha", "away_team": "Beta",
            "home_win": 0.30, "draw": 0.40, "away_win": 0.30}
    s = plain_summary(pred)
    print(f"  draw case -> {s}")
    assert "evenly matched" in s.lower()
    assert not _banned_hits(s)
    return True


def test_no_banned_words_in_interface_strings():
    """Every UI string in every language must be clean.

    The payload test covers what the engine publishes; this covers what the app
    itself says. A banned word slipped in through a new analytics heading -
    "How sure we were" - which no payload check would ever have seen, because
    it lives only in the frontend.
    """
    src = (ROOT / "app" / "src" / "i18n.ts").read_text(encoding="utf-8")
    # Only the quoted string VALUES, not keys or comments.
    values = re.findall(r':\s*"((?:[^"\\]|\\.)*)"', src)
    hits = []
    for v in values:
        for w in _banned_hits(v):
            hits.append(f"{w!r} in {v[:60]!r}")
    print(f"  {len(values)} interface strings checked across all languages")
    assert not hits, "banned words in interface text: " + "; ".join(hits)
    return True


def main():
    tests = [
        ("payload keys match schema.sql", test_schema_match),
        ("three-way percentages", test_percentages),
        ("both-teams-score is not published", test_btts_not_published),
        ("over/under gated to leagues with an edge", test_over_under_gating),
        ("no banned words", test_no_banned_words),
        ("no certainty claims", test_no_certainty_claims),
        ("confidence bands", test_confidence_bands),
        ("draw-favoured summary", test_summary_draw_case),
        ("no banned words in any interface string", test_no_banned_words_in_interface_strings),
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
