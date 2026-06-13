#!/usr/bin/env python3
"""
Initialise a new athlete under ~/.runforlife/athletes/<user>/.

Creates the athlete dir and a tokens/ subdir (mode 0700), then seeds a
template profile.json plus empty insights/ephemeral/feedback files. Existing
files are left untouched, so this is safe to re-run.

Run from the repo root with:
    uv run python runforlife-coach/scripts/athlete_init.py --user <name>
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from runforlife.storage.athlete_memory import atomic_write_json  # noqa: E402
from runforlife.storage.paths import (  # noqa: E402
    athlete_dir,
    ephemeral_path,
    feedback_path,
    insights_path,
    profile_path,
    tokens_dir,
)


def _template_profile(user: str) -> dict:
    """Minimal profile skeleton the athlete can flesh out by hand."""
    return {
        "name": user,
        "age": None,
        "watch": "Garmin Forerunner 165",
        "goals": {},
        "prefs": {},
    }


def _seed(path: Path, data: dict, label: str) -> None:
    if path.exists():
        print(f"  skip {label}: already exists")
        return
    atomic_write_json(path, data)
    print(f"  created {label} -> {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialise a new athlete.")
    parser.add_argument("--user", required=True, help="Athlete name.")
    args = parser.parse_args()
    user = args.user

    base = athlete_dir(user)
    print(f"Initialising athlete '{user}' at {base}")

    tdir = tokens_dir(user)
    print(f"  tokens dir ready (mode 0700) -> {tdir}")

    _seed(profile_path(user), _template_profile(user), "profile.json")
    _seed(insights_path(user), {"insights": []}, "insights.json")
    _seed(ephemeral_path(user), {"items": []}, "ephemeral.json")
    _seed(feedback_path(user), {"items": []}, "feedback.json")

    print("Done.")


if __name__ == "__main__":
    main()
