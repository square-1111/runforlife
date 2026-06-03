#!/usr/bin/env python3
"""
Migrate legacy per-user data into the new ~/.runforlife/athletes/<user>/ layout.

For each athlete this script:
  - copies metrics.db, banister.json, personality.json, profile.json from the
    legacy DATA_DIR/<user> dir into the new athlete dir (only if not already there)
  - reads the legacy memory.db 'memories' table and splits rows into:
        insights.json   <- rows where expires_on IS NULL
        ephemeral.json  <- rows where expires_on is set
  - creates an empty feedback.json

It is idempotent: existing target files are left untouched, and the memory
split is skipped when insights/ephemeral already hold content.

Run from the repo root with: uv run python runforlife-coach/scripts/migrate_data.py
DO NOT run automatically — this is a one-shot data migration.
"""

import argparse
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from runforlife.config import USERS  # noqa: E402
from runforlife.storage.paths import (  # noqa: E402
    athlete_dir,
    banister_path,
    ephemeral_path,
    feedback_path,
    insights_path,
    legacy_user_dir,
    metrics_db_path,
    personality_path,
    profile_path,
)

# Legacy memory rows are split by these created-at / expiry semantics.
_COPY_FILES = ("metrics.db", "banister.json", "personality.json", "profile.json")


def _atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON atomically: temp file in the same dir + os.replace."""
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


def _target_for(user: str, filename: str) -> Path:
    """Map a legacy filename to its new athlete-dir path."""
    mapping = {
        "metrics.db": metrics_db_path(user),
        "banister.json": banister_path(user),
        "personality.json": personality_path(user),
        "profile.json": profile_path(user),
    }
    return mapping[filename]


def _copy_known_files(user: str, dry_run: bool, report: list[str]) -> None:
    src_dir = legacy_user_dir(user)
    for filename in _COPY_FILES:
        src = src_dir / filename
        dst = _target_for(user, filename)
        if not src.exists():
            report.append(f"  skip {filename}: no legacy source")
            continue
        if dst.exists():
            report.append(f"  skip {filename}: target already exists")
            continue
        if dry_run:
            report.append(f"  WOULD copy {filename} -> {dst}")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        report.append(f"  copied {filename} -> {dst}")


def _read_legacy_memories(memory_db: Path) -> list[dict]:
    """Read rows from the legacy 'memories' table; empty list if absent."""
    if not memory_db.exists():
        return []
    conn = sqlite3.connect(str(memory_db))
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='memories'"
        )
        if cursor.fetchone() is None:
            return []
        rows = conn.execute(
            "SELECT id, content, expires_on, created_at FROM memories ORDER BY id"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _split_memories(user: str, dry_run: bool, report: list[str]) -> None:
    legacy_memory = legacy_user_dir(user) / "memory.db"
    rows = _read_legacy_memories(legacy_memory)

    insights_dst = insights_path(user)
    ephemeral_dst = ephemeral_path(user)

    if insights_dst.exists() or ephemeral_dst.exists():
        report.append("  skip memory split: insights/ephemeral already present")
    elif not rows:
        report.append("  memory split: no legacy memories found")
    else:
        insights: list[dict] = []
        ephemeral: list[dict] = []
        for row in rows:
            expires_on = row["expires_on"]
            created_at = (row["created_at"] or "")[:10] or None
            if expires_on is None:
                insights.append({
                    "id": len(insights) + 1,
                    "insight": row["content"],
                    "type": "migrated",
                    "confidence": 0.5,
                    "discovered": created_at,
                    "last_reinforced": created_at,
                })
            else:
                ephemeral.append({
                    "id": len(ephemeral) + 1,
                    "content": row["content"],
                    "expires_on": expires_on,
                    "created_at": created_at,
                })
        report.append(
            f"  memory split: {len(insights)} insights, {len(ephemeral)} ephemeral"
        )
        if not dry_run:
            _atomic_write_json(insights_dst, {"insights": insights})
            _atomic_write_json(ephemeral_dst, {"items": ephemeral})

    # Always ensure an empty feedback.json exists.
    feedback_dst = feedback_path(user)
    if feedback_dst.exists():
        report.append("  skip feedback.json: already exists")
    elif dry_run:
        report.append(f"  WOULD create empty feedback.json -> {feedback_dst}")
    else:
        _atomic_write_json(feedback_dst, {"items": []})
        report.append(f"  created empty feedback.json -> {feedback_dst}")


def migrate_user(user: str, dry_run: bool) -> None:
    print(f"\n=== {user} ===")
    print(f"  legacy source: {legacy_user_dir(user)}")
    if not dry_run:
        print(f"  athlete dir:   {athlete_dir(user)}")
    report: list[str] = []
    _copy_known_files(user, dry_run, report)
    _split_memories(user, dry_run, report)
    for line in report:
        print(line)


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate legacy data into ~/.runforlife.")
    parser.add_argument("--user", default=None, help="Single athlete (default: all USERS).")
    parser.add_argument("--dry-run", action="store_true", help="Report without writing.")
    args = parser.parse_args()

    users = (args.user,) if args.user else USERS
    if args.user and args.user not in USERS:
        print(f"Warning: '{args.user}' is not in USERS {USERS}; proceeding anyway.")

    mode = "DRY RUN" if args.dry_run else "LIVE"
    print(f"RunForLife data migration [{mode}] for: {', '.join(users)}")

    for user in users:
        migrate_user(user, args.dry_run)

    print("\nDone." + (" (no files written)" if args.dry_run else ""))


if __name__ == "__main__":
    main()
