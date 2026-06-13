#!/usr/bin/env python3
"""
Inspect and manage an athlete's four memory files.

Operates on insights.json / ephemeral.json / feedback.json via the
athlete_memory API. Usage (from the repo root):

    uv run python runforlife-coach/scripts/memory_manager.py --user <name> --list
    uv run python runforlife-coach/scripts/memory_manager.py --user <name> --show insights
    uv run python runforlife-coach/scripts/memory_manager.py --user <name> --delete ephemeral 3
    uv run python runforlife-coach/scripts/memory_manager.py --user <name> --prune-expired
    uv run python runforlife-coach/scripts/memory_manager.py --user <name> --add-feedback \
        --advice-type deload --advice "Skip Push, easy 3km" --rating positive \
        --adherence followed --outcome "felt fresh next day, HRV up"
    uv run python runforlife-coach/scripts/memory_manager.py --user <name> --add-insight \
        --insight "Responds well to back-to-back easy days after races" \
        --insight-type recovery --confidence 0.7
    uv run python runforlife-coach/scripts/memory_manager.py --user <name> --add-ephemeral \
        --content "Travelling Mon-Fri, treadmill only" --expires-on 2026-06-20

Categories: insights | ephemeral | feedback
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from runforlife.storage import athlete_memory  # noqa: E402
from runforlife.storage.athlete_memory import atomic_write_json  # noqa: E402
from runforlife.storage.paths import (  # noqa: E402
    ephemeral_path,
    feedback_path,
    insights_path,
)

_CATEGORIES = ("insights", "ephemeral", "feedback")
_ENVELOPE_KEY = {"insights": "insights", "ephemeral": "items", "feedback": "items"}
_PATH_FOR = {
    "insights": insights_path,
    "ephemeral": ephemeral_path,
    "feedback": feedback_path,
}


def _load_all(user: str, category: str) -> list[dict]:
    """Load every record in a category (no expiry filtering)."""
    loaders = {
        "insights": athlete_memory.load_insights,
        "feedback": athlete_memory.load_feedback,
    }
    if category == "ephemeral":
        # load_active_ephemeral filters expired; for management we want all rows.
        path = ephemeral_path(user)
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8")).get("items", [])
    return loaders[category](user)


def _print_records(category: str, records: list[dict]) -> None:
    if not records:
        print(f"  ({category}: empty)")
        return
    for record in records:
        print(f"  [{record.get('id')}] {json.dumps(record, ensure_ascii=False)}")


def _cmd_list(user: str) -> None:
    for category in _CATEGORIES:
        records = _load_all(user, category)
        print(f"{category} ({len(records)}):")
        _print_records(category, records)


def _cmd_show(user: str, category: str) -> None:
    records = _load_all(user, category)
    print(f"{category} ({len(records)}):")
    _print_records(category, records)


def _cmd_delete(user: str, category: str, record_id: int) -> None:
    path = _PATH_FOR[category](user)
    key = _ENVELOPE_KEY[category]
    if not path.exists():
        print(f"Nothing to delete: {category} file does not exist.")
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get(key, [])
    kept = [item for item in items if int(item.get("id", -1)) != record_id]
    if len(kept) == len(items):
        print(f"No {category} record with id {record_id}.")
        return
    data[key] = kept
    atomic_write_json(path, data)
    print(f"Deleted {category} id {record_id}.")


def _cmd_prune(user: str) -> None:
    removed = athlete_memory.prune_ephemeral(user)
    print(f"Pruned {removed} expired ephemeral item(s).")


def _cmd_add_feedback(
    user: str,
    advice_type: str,
    advice: str,
    rating: str,
    adherence: str | None,
    outcome: str | None,
) -> None:
    """Append one feedback record so /reflect has something to learn from.

    This is the capture step the self-evolution loop was missing: advice was
    given for weeks but never recorded, so feedback_stats.py always tallied
    zero. Records flow through athlete_memory.add_feedback (atomic write,
    auto-incrementing id) into the same feedback.json that /reflect reads.
    """
    new_id = athlete_memory.add_feedback(
        user,
        advice_type=advice_type,
        advice=advice,
        rating=rating,
        adherence=adherence,
        outcome=outcome,
    )
    print(f"Recorded feedback id {new_id} for {user} (advice_type={advice_type}, rating={rating}).")


def _cmd_add_insight(
    user: str,
    insight: str,
    insight_type: str,
    confidence: float,
) -> None:
    """Append one learned insight via athlete_memory.add_insight.

    Insights are the long-lived, high-confidence things the coach has learned
    about an athlete (e.g. "responds well to back-to-back easy days"). They flow
    through the same atomic-write, auto-incrementing-id path as feedback into
    insights.json, which the coach reads to stay grounded.
    """
    new_id = athlete_memory.add_insight(
        user,
        insight=insight,
        type=insight_type,
        confidence=confidence,
    )
    print(
        f"Recorded insight id {new_id} for {user} "
        f"(type={insight_type}, confidence={confidence})."
    )


def _cmd_add_ephemeral(
    user: str,
    content: str,
    expires_on: str | None,
) -> None:
    """Append one short-lived context item via athlete_memory.add_ephemeral.

    Ephemeral items capture transient reality — injury, travel, a life event, a
    supplement change — with an optional expiry so stale context auto-drops out
    of advice (and /switch's prune sweeps it). Returns the new item's id.
    """
    new_id = athlete_memory.add_ephemeral(
        user,
        content=content,
        expires_on=expires_on,
    )
    expiry = expires_on if expires_on else "no expiry"
    print(f"Recorded ephemeral id {new_id} for {user} ({expiry}).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage an athlete's memory files.")
    parser.add_argument("--user", required=True, help="Athlete name.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="List all categories.")
    group.add_argument("--show", metavar="CATEGORY", choices=_CATEGORIES,
                       help="Show one category.")
    group.add_argument("--delete", nargs=2, metavar=("CATEGORY", "ID"),
                       help="Delete a record by category and id.")
    group.add_argument("--prune-expired", action="store_true",
                       help="Delete expired ephemeral items.")
    group.add_argument("--add-feedback", action="store_true",
                       help="Record one coaching-feedback item (capture step for "
                            "/reflect). Requires --advice-type, --advice, --rating; "
                            "--adherence and --outcome are optional.")
    group.add_argument("--add-insight", action="store_true",
                       help="Record one learned insight about the athlete. Requires "
                            "--insight and --insight-type; --confidence is optional "
                            "(default 0.5).")
    group.add_argument("--add-ephemeral", action="store_true",
                       help="Record one short-lived context item (injury, travel, life "
                            "event, supplement change). Requires --content; --expires-on "
                            "(YYYY-MM-DD) is optional.")
    # Field values for --add-feedback (ignored by the other actions).
    parser.add_argument("--advice-type", help="Category, e.g. 'rest_day', 'tempo', 'deload'.")
    parser.add_argument("--advice", help="The advice that was given (short text).")
    parser.add_argument("--rating", help="How it landed, e.g. 'positive' | 'neutral' | 'negative'.")
    parser.add_argument("--adherence", help="Optional: 'followed' | 'partial' | 'ignored'.")
    parser.add_argument("--outcome", help="Optional: what actually happened afterward.")
    # Field values for --add-insight.
    parser.add_argument("--insight", help="The insight text (what was learned).")
    parser.add_argument("--insight-type", help="Insight category, e.g. 'recovery', 'pacing'.")
    parser.add_argument("--confidence", type=float, default=0.5,
                        help="Optional: confidence 0.0-1.0 (default 0.5).")
    # Field values for --add-ephemeral.
    parser.add_argument("--content", help="The short-lived context item (short text).")
    parser.add_argument("--expires-on", help="Optional: expiry date as YYYY-MM-DD.")
    args = parser.parse_args()

    if args.list:
        _cmd_list(args.user)
    elif args.show:
        _cmd_show(args.user, args.show)
    elif args.delete:
        category, raw_id = args.delete
        if category not in _CATEGORIES:
            parser.error(f"category must be one of {_CATEGORIES}")
        try:
            record_id = int(raw_id)
        except ValueError:
            parser.error("ID must be an integer")
        _cmd_delete(args.user, category, record_id)
    elif args.prune_expired:
        _cmd_prune(args.user)
    elif args.add_feedback:
        missing = [
            flag for flag, value in (
                ("--advice-type", args.advice_type),
                ("--advice", args.advice),
                ("--rating", args.rating),
            )
            if not value
        ]
        if missing:
            parser.error("--add-feedback requires " + ", ".join(missing))
        _cmd_add_feedback(
            args.user,
            args.advice_type,
            args.advice,
            args.rating,
            args.adherence,
            args.outcome,
        )
    elif args.add_insight:
        missing = [
            flag for flag, value in (
                ("--insight", args.insight),
                ("--insight-type", args.insight_type),
            )
            if not value
        ]
        if missing:
            parser.error("--add-insight requires " + ", ".join(missing))
        _cmd_add_insight(
            args.user,
            args.insight,
            args.insight_type,
            args.confidence,
        )
    elif args.add_ephemeral:
        if not args.content:
            parser.error("--add-ephemeral requires --content")
        if args.expires_on is not None:
            try:
                date.fromisoformat(args.expires_on)
            except ValueError:
                parser.error("--expires-on must be a valid date in YYYY-MM-DD format")
        _cmd_add_ephemeral(
            args.user,
            args.content,
            args.expires_on,
        )


if __name__ == "__main__":
    main()
