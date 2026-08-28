"""One-paragraph summary of a scheduled run, shown on the GitHub Actions page.

Its job is to make the most common non-failure legible. Zero upcoming fixtures
looks like a broken job and almost never is: football-data publishes fixtures
only a few days before each round.
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "output"


def main() -> None:
    meta = OUT / "meta.json"
    print("### Forecast run\n")
    if not meta.exists():
        print("No output was produced. Check the steps above for an error.")
        return

    m = json.loads(meta.read_text(encoding="utf-8"))
    print(f"- Upcoming fixtures: **{m.get('upcoming', 0)}**")
    print(f"- Settled matches: **{m.get('settled', 0)}**")
    print(f"- Published: {m.get('published_at', 'unknown')}")

    if not m.get("upcoming"):
        print()
        print("> No upcoming fixtures is usually **not** a fault. Football-data "
              "publishes fixtures only a few days before each round, so between "
              "rounds there is genuinely nothing to forecast.")


if __name__ == "__main__":
    main()
