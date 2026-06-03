#!/usr/bin/env python3
"""
Inspect and manage an athlete's four memory files.

Operates on insights.json / ephemeral.json / feedback.json via the
athlete_memory API. Usage (from the repo root):

    uv run python runforlife-coach/scripts/memory_manager.py --user <name> --list
    uv run python runforlife-coach/scripts/memory_manager.py --user <name> --show insights
    uv run python runforlife-coach/scripts/memory_manager.py --user <name> --delete ephemeral 3
    uv run python runforlife-coach/scripts/memory_manager.py --user <name> --prune-expired

Categories: insights | ephemeral | feedback
"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from runforlife.storage import athlete_memory  # noqa: E402
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


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
        os.replace(tmp_name, path)
    except BaseException:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise


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
    _atomic_write_json(path, data)
    print(f"Deleted {category} id {record_id}.")


def _cmd_prune(user: str) -> None:
    removed = athlete_memory.prune_ephemeral(user)
    print(f"Pruned {removed} expired ephemeral item(s).")


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


if __name__ == "__main__":
    main()
