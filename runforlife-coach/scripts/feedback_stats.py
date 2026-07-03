"""
Deterministic aggregation of an athlete's coaching feedback.

Reads ~/.runforlife/athletes/<user>/feedback.json and emits explicit SUCCESS and
adherence rates per advice type as JSON. The reflection step (the /reflect
command) reads this — the LLM never tallies or averages outcomes itself; this
script owns the arithmetic.

Per advice type it computes:
  - ratings_normalized: rating counts after collapsing typos/casing onto the
    {positive, neutral, negative} enum,
  - unrecognized_ratings: ratings that didn't map to the enum, counted (never
    silently dropped) so noise is visible,
  - success_rate: positives / (positives + negatives) — neutral and unrecognized
    are excluded from the denominator; None when there is no positive/negative
    signal,
  - adherence_rate: a 0..1 score over rows with a known adherence value
    (followed=1.0, partial=0.5, ignored=0.0); None when none are known.

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

from runforlife.storage import athlete_memory  # noqa: E402

# Map free-text ratings onto a small enum so typos/casing don't fragment buckets.
_RATING_ENUM = ("positive", "neutral", "negative")
_RATING_ALIASES = {
    "positive": "positive",
    "pos": "positive",
    "good": "positive",
    "great": "positive",
    "+": "positive",
    "yes": "positive",
    "neutral": "neutral",
    "neut": "neutral",
    "ok": "neutral",
    "okay": "neutral",
    "meh": "neutral",
    "mixed": "neutral",
    "negative": "negative",
    "neg": "negative",
    "bad": "negative",
    "poor": "negative",
    "-": "negative",
    "no": "negative",
}

# Map adherence values onto a 0..1 weight; unknown values don't count.
_ADHERENCE_WEIGHTS = {
    "followed": 1.0,
    "full": 1.0,
    "yes": 1.0,
    "partial": 0.5,
    "partially": 0.5,
    "some": 0.5,
    "ignored": 0.0,
    "skipped": 0.0,
    "no": 0.0,
}


def normalize_rating(rating: object) -> str | None:
    """Collapse a free-text rating to the {positive,neutral,negative} enum.

    Returns the canonical enum value, or None if the rating is unrecognized
    (the caller counts those separately rather than dropping them).
    """
    if rating is None:
        return None
    key = str(rating).strip().lower()
    return _RATING_ALIASES.get(key)


def normalize_adherence(adherence: object) -> float | None:
    """Map an adherence value to a 0..1 weight, or None if unrecognized."""
    if adherence is None:
        return None
    key = str(adherence).strip().lower()
    return _ADHERENCE_WEIGHTS.get(key)


def aggregate(user: str) -> dict:
    """Group feedback by advice_type and tally ratings / adherence / outcomes.

    Adds explicit success_rate and adherence_rate per advice type on top of the
    original raw tallies (which are kept for backward compatibility).
    """
    items = athlete_memory.load_feedback(user)

    by_type: dict[str, dict] = {}
    for item in items:
        advice_type = (item.get("advice_type") or "unspecified").strip() or "unspecified"
        bucket = by_type.setdefault(
            advice_type,
            {
                "n": 0,
                "ratings": Counter(),
                "ratings_normalized": Counter(),
                "unrecognized_ratings": Counter(),
                "adherence": Counter(),
                "_adherence_weight_sum": 0.0,
                "adherence_n": 0,
                "sample_outcomes": [],
            },
        )
        bucket["n"] += 1

        rating = item.get("rating")
        if rating:
            bucket["ratings"][str(rating)] += 1
            canonical = normalize_rating(rating)
            if canonical is None:
                bucket["unrecognized_ratings"][str(rating)] += 1
            else:
                bucket["ratings_normalized"][canonical] += 1

        adherence = item.get("adherence")
        if adherence:
            bucket["adherence"][str(adherence)] += 1
            weight = normalize_adherence(adherence)
            if weight is not None:
                bucket["_adherence_weight_sum"] += weight
                bucket["adherence_n"] += 1

        outcome = item.get("outcome")
        if outcome and len(bucket["sample_outcomes"]) < 5:
            bucket["sample_outcomes"].append(str(outcome))

    # Finalize each bucket: Counters -> dicts, compute rates.
    for bucket in by_type.values():
        normalized = bucket["ratings_normalized"]
        positives = normalized.get("positive", 0)
        negatives = normalized.get("negative", 0)
        rated_n = positives + negatives
        bucket["rated_n"] = rated_n
        bucket["success_rate"] = (positives / rated_n) if rated_n else None

        adherence_n = bucket["adherence_n"]
        weight_sum = bucket.pop("_adherence_weight_sum")
        bucket["adherence_rate"] = (weight_sum / adherence_n) if adherence_n else None

        bucket["ratings"] = dict(bucket["ratings"])
        bucket["ratings_normalized"] = dict(normalized)
        bucket["unrecognized_ratings"] = dict(bucket["unrecognized_ratings"])
        bucket["adherence"] = dict(bucket["adherence"])

    return {
        "user": user,
        "total_feedback": len(items),
        "advice_types": len(by_type),
        "by_advice_type": by_type,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate coaching feedback by advice type.")
    parser.add_argument("--user", required=True, help="Athlete handle.")
    args = parser.parse_args()

    try:
        result = aggregate(args.user)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
