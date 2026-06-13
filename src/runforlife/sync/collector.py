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

import logging
import time

from runforlife.skills.data.garmin_auth import get_session

logger = logging.getLogger(__name__)

# The data sources fetched per day. Kept explicit so ingest can tell a real
# "no data" day from one where every fetch errored, and so a provenance map can
# be returned without polluting the source-key set.
SOURCE_KEYS = ("sleep", "hrv", "summary", "activities", "vo2max")


def collect_day(user: str, date: str, delay_seconds: float = 0.3) -> dict:
    """
    Collect all metrics for a single user/date.

    Returns dict with keys: sleep, hrv, summary, activities, vo2max — each the
    raw API response dict, or None on error — plus a `_provenance` map
    {source: "ok" | "empty" | "error:<Type>"} so a transient fetch failure is
    distinguishable from a genuine rest/no-data day (previously both looked
    identical, which is how partial fetches wrote skeleton rows silently).
    """
    garmin = get_session(user)
    results: dict = {}
    provenance: dict[str, str] = {}

    def _fetch(key: str, fn, *args, **kwargs):
        try:
            value = fn(*args, **kwargs)
            results[key] = value
            provenance[key] = "ok" if value is not None else "empty"
        except Exception as e:  # noqa: BLE001 - soft-fail per source, but now LOGGED
            results[key] = None
            provenance[key] = f"error:{type(e).__name__}"
            logger.warning(
                "collect_day soft-fail user=%s date=%s source=%s error=%s",
                user, date, key, e,
            )
        time.sleep(delay_seconds)

    _fetch("sleep",      garmin.get_sleep_data,          date)
    _fetch("hrv",        garmin.get_hrv_data,            date)
    _fetch("summary",    garmin.get_user_summary,        date)
    _fetch("activities", garmin.get_activities_by_date,  date, date)
    _fetch("vo2max",     garmin.get_max_metrics,         date)

    errored = [k for k, v in provenance.items() if v.startswith("error")]
    if errored:
        logger.warning(
            "collect_day user=%s date=%s INCOMPLETE — failed sources=%s",
            user, date, errored,
        )

    results["_provenance"] = provenance
    return results
