#!/usr/bin/env python3
"""
Initialise a new athlete under RUNFORLIFE_HOME/athletes/<handle>/.

Writes a full, valid profile.json (a caller-supplied dict verbatim, or a
sensible default built from name/gender/units) plus empty insights/ephemeral/
feedback files. Existing files are left untouched, so this is safe to re-run.

Does NOT create a tokens/ subdir under the athlete: Garmin auth writes cached
tokens to repo/tokens/<handle>/ (config.TOKENS_DIR), so the per-athlete tokens
dir under ~/.runforlife was dead and only caused confusion.

Run from the repo root with:
    uv run python ./runforlife-coach/scripts/athlete_init.py --user <handle> [--name ...]
Or pass a fully-assembled profile (used by /onboard):
    ... --user <handle> --profile-file /path/to/profile.json
"""

import argparse
import json
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
)

DEFAULT_WATCH = "Garmin Forerunner 165"


def build_default_profile(
    handle: str,
    *,
    name: str | None = None,
    gender: str | None = None,
    units: str = "metric",
    watch: str = DEFAULT_WATCH,
) -> dict:
    """A minimal-but-valid profile matching the shape the playbooks read.

    Goals are left empty (collected progressively after first value); the coach
    still works day one. `garmin_user` must equal the handle — that's the key
    the sync/auth layer uses.
    """
    return {
        "name": name or handle,
        "gender": gender,
        "garmin_user": handle,
        "goals": {},
        "context": {"watch": watch},
        "prefs": {"units": units},
    }


def _seed(path: Path, data: dict, label: str) -> None:
    if path.exists():
        print(f"  skip {label}: already exists")
        return
    atomic_write_json(path, data)
    print(f"  created {label} -> {path}")


def init_athlete(handle: str, *, profile: dict | None = None, **profile_fields) -> None:
    """Scaffold an athlete's dir + profile + empty memory files (idempotent).

    `profile` (a full dict) is written verbatim; otherwise a default is built
    from `profile_fields` (name / gender / units / watch).
    """
    base = athlete_dir(handle)
    print(f"Initialising athlete '{handle}' at {base}")

    prof = profile if profile is not None else build_default_profile(handle, **profile_fields)
    _seed(profile_path(handle), prof, "profile.json")
    _seed(insights_path(handle), {"insights": []}, "insights.json")
    _seed(ephemeral_path(handle), {"items": []}, "ephemeral.json")
    _seed(feedback_path(handle), {"items": []}, "feedback.json")
    print("Done.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialise a new athlete.")
    parser.add_argument("--user", required=True, help="Athlete handle.")
    parser.add_argument("--name", default=None, help="Display name (default: handle).")
    parser.add_argument("--gender", default=None, help="male / female / other.")
    parser.add_argument("--units", default="metric", help="metric or imperial.")
    parser.add_argument("--watch", default=DEFAULT_WATCH, help="Watch model.")
    parser.add_argument(
        "--profile-file", default=None,
        help="Path to a JSON file with a full profile dict to write verbatim "
             "(overrides the field flags). Used by /onboard.",
    )
    args = parser.parse_args()

    profile = None
    if args.profile_file:
        profile = json.loads(Path(args.profile_file).read_text(encoding="utf-8"))

    init_athlete(
        args.user,
        profile=profile,
        name=args.name,
        gender=args.gender,
        units=args.units,
        watch=args.watch,
    )


if __name__ == "__main__":
    main()
