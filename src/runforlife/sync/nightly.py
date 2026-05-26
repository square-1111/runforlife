"""
Nightly sync entrypoint — designed for cron execution.

Usage:
  # Sync yesterday (cron daily):
  uv run python -m runforlife.sync.nightly --user tezuesh
  uv run python -m runforlife.sync.nightly --user kakul

  # Full history backfill (run once):
  uv run python -m runforlife.sync.nightly --user tezuesh --backfill
  uv run python -m runforlife.sync.nightly --user all --backfill

  # Custom date range:
  uv run python -m runforlife.sync.nightly --user tezuesh --start 2026-01-01 --end 2026-05-25

Garmin rate limits:
  1.5s delay between API calls within a day, 2s between days.
  Full backfill of 1 year ≈ 365 days × 7 calls × 1.5s ≈ ~64 minutes.
"""

import argparse
import time
from datetime import date, timedelta

from dotenv import load_dotenv

from runforlife.config import USERS
from runforlife.skills.data.garmin_auth import GarminAuth
from runforlife.storage.metrics_store import count_days, has_day
from runforlife.sync.ingest import ingest_day

_AUTH_SKILL = GarminAuth()


def _authenticate(user: str) -> bool:
    result = _AUTH_SKILL.execute(user=user)
    if not result.get("success"):
        print(f"  [AUTH FAILED] {user}: {result.get('error')}")
        return False
    print(f"  [AUTH OK] {user} ({result.get('method')})")
    return True


def sync_user(user: str, start_date: str, end_date: str) -> None:
    """Sync all dates in [start_date, end_date] for a single user."""
    print(f"\n=== Syncing {user}: {start_date} → {end_date} ===")

    if not _authenticate(user):
        return

    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)

    current = start
    success_count = 0
    skip_count = 0
    error_count = 0

    while current <= end:
        date_str = current.isoformat()

        if has_day(user, date_str):
            skip_count += 1
            current += timedelta(days=1)
            continue

        try:
            doc = ingest_day(user, date_str, delay_seconds=1.5)
            if doc:
                print(f"  [OK] {date_str}: HRV={doc.hrv_last_night}, readiness={doc.readiness_score}, run={doc.run_distance_km}km")
                success_count += 1
            else:
                print(f"  [EMPTY] {date_str}: no data available")
                error_count += 1
        except Exception as e:
            print(f"  [ERROR] {date_str}: {e}")
            error_count += 1

        time.sleep(2.0)
        current += timedelta(days=1)

    print(f"\n  Done: {success_count} ingested, {skip_count} skipped, {error_count} errors")
    print(f"  Total days in DB: {count_days(user)}")


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="RunForLife nightly sync")
    parser.add_argument(
        "--user",
        required=True,
        choices=list(USERS) + ["all"],
        help="User to sync, or 'all' for both",
    )
    parser.add_argument("--backfill", action="store_true", help="Backfill from 2025-01-01")
    parser.add_argument("--start", help="Start date YYYY-MM-DD (overrides --backfill)")
    parser.add_argument("--end", help="End date YYYY-MM-DD (default: yesterday)")
    args = parser.parse_args()

    today = date.today()
    yesterday = (today - timedelta(days=1)).isoformat()

    end_date = args.end or yesterday

    if args.start:
        start_date = args.start
    elif args.backfill:
        start_date = "2025-01-01"
    else:
        start_date = yesterday

    users_to_sync = list(USERS) if args.user == "all" else [args.user]

    for user in users_to_sync:
        sync_user(user, start_date, end_date)

    print("\nSync complete.")


if __name__ == "__main__":
    main()
