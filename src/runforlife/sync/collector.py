"""
Data collector for the nightly sync pipeline.

Calls Garmin API directly for a single date and returns a raw dict
that ingest.py maps to a DailyDocument.

Key design: get_user_summary is a single call that provides RHR, stress,
body battery, and steps — replacing 3 previously broken individual calls.

Call budget per day (was 7, now 5):
  1. get_sleep_data       — sleep stages, score, bedtime, sleep HR
  2. get_hrv_data         — HRV nightly avg + weekly avg + baseline + status
  3. get_user_summary     — RHR, stress, body battery, steps, calories
  4. get_activities       — run details (pace, HR, training effect)
  5. get_max_metrics      — VO2max daily estimate

Errors are soft — a missing metric produces None, not a crash.
"""

import time

from runforlife.skills.data.garmin_auth import get_session


def collect_day(user: str, date: str, delay_seconds: float = 0.3) -> dict:
    """
    Collect all metrics for a single user/date.

    Returns dict with keys: sleep, hrv, summary, activities, vo2max.
    Each value is the raw API response dict, or None on error.
    """
    garmin = get_session(user)
    results: dict = {}

    def _fetch(key: str, fn, *args, **kwargs):
        try:
            results[key] = fn(*args, **kwargs)
        except Exception:
            results[key] = None
        time.sleep(delay_seconds)

    _fetch("sleep",      garmin.get_sleep_data,          date)
    _fetch("hrv",        garmin.get_hrv_data,            date)
    _fetch("summary",    garmin.get_user_summary,        date)
    _fetch("activities", garmin.get_activities_by_date,  date, date)
    _fetch("vo2max",     garmin.get_max_metrics,         date)

    return results
