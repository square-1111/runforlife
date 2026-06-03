"""
Deterministic aggregation of an athlete's coaching feedback.

Reads ~/.runforlife/athletes/<user>/feedback.json and emits success-rate-by-
advice-type as JSON. The reflection step (the /reflect command) reads this — the
LLM never tallies or averages outcomes itself; this script owns the arithmetic.

Usage:
    uv run python runforlife-coach/scripts/feedback_stats.py --user tezuesh
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

# Make the runforlife package importable when run from the plugin dir.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from runforlife.config import USERS  # noqa: E402
from runforlife.storage import athlete_memory  # noqa: E402


def aggregate(user: str) -> dict:
    """Group feedback by advice_type and tally ratings / adherence / outcomes."""
    items = athlete_memory.load_feedback(user)

    by_type: dict[str, dict] = {}
    for item in items:
        advice_type = (item.get("advice_type") or "unspecified").strip() or "unspecified"
        bucket = by_type.setdefault(
            advice_type,
            {"n": 0, "ratings": Counter(), "adherence": Counter(), "sample_outcomes": []},
        )
        bucket["n"] += 1

        rating = item.get("rating")
        if rating:
            bucket["ratings"][str(rating)] += 1

        adherence = item.get("adherence")
        if adherence:
            bucket["adherence"][str(adherence)] += 1

        outcome = item.get("outcome")
        if outcome and len(bucket["sample_outcomes"]) < 5:
            bucket["sample_outcomes"].append(str(outcome))

    # Counters -> plain dicts for JSON
    for bucket in by_type.values():
        bucket["ratings"] = dict(bucket["ratings"])
        bucket["adherence"] = dict(bucket["adherence"])

    return {
        "user": user,
        "total_feedback": len(items),
        "advice_types": len(by_type),
        "by_advice_type": by_type,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate coaching feedback by advice type.")
    parser.add_argument("--user", required=True, choices=list(USERS))
    args = parser.parse_args()

    try:
        result = aggregate(args.user)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
