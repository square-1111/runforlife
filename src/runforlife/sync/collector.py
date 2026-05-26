"""
Data collector for the nightly sync pipeline.

Calls existing Garmin skills for a single date and returns
raw data dict that ingest.py maps to a DailyDocument.

We call skill.execute() directly rather than going through the agent loop —
this is intentional. The agent loop exists for LLM-driven tool calls.
The sync pipeline runs autonomously without an LLM in the loop.

Errors are soft — a missing metric produces None, not a crash.
The document gets stored with whatever data was available.
"""

import time

from runforlife.skills.data.fetch_activities import FetchActivities
from runforlife.skills.data.fetch_body_battery import FetchBodyBattery
from runforlife.skills.data.fetch_heart_rate import FetchHeartRate
from runforlife.skills.data.fetch_hrv import FetchHRV
from runforlife.skills.data.fetch_sleep import FetchSleep
from runforlife.skills.data.fetch_training_readiness import FetchTrainingReadiness
from runforlife.skills.data.fetch_training_status import FetchTrainingStatus

_sleep_skill = FetchSleep()
_hrv_skill = FetchHRV()
_hr_skill = FetchHeartRate()
_training_status_skill = FetchTrainingStatus()
_training_readiness_skill = FetchTrainingReadiness()
_activities_skill = FetchActivities()
_body_battery_skill = FetchBodyBattery()


def collect_day(user: str, date: str, delay_seconds: float = 1.0) -> dict:
    """
    Collect all metrics for a single user/date.

    delay_seconds: pause between API calls to respect Garmin rate limits.
    Returns dict with keys: sleep, hrv, heart_rate, training_status,
    training_readiness, activities, body_battery. Each may be None on error.
    """
    results: dict = {}

    def _fetch(key: str, skill, **kwargs):
        try:
            r = skill.execute(**kwargs)
            results[key] = r if r.get("success") else None
        except Exception as e:
            results[key] = None
        time.sleep(delay_seconds)

    _fetch("sleep", _sleep_skill, user=user, date=date)
    _fetch("hrv", _hrv_skill, user=user, date=date)
    _fetch("heart_rate", _hr_skill, user=user, date=date)
    _fetch("training_status", _training_status_skill, user=user, date=date)
    _fetch("training_readiness", _training_readiness_skill, user=user, date=date)
    _fetch("body_battery", _body_battery_skill, user=user, start_date=date, end_date=date)
    # Activities: fetch running for this specific date only
    _fetch("activities", _activities_skill, user=user, start_date=date, end_date=date, activity_type="running")

    return results


def extract_sleep_efficiency(sleep_data: dict | None) -> float | None:
    """Pull sleep efficiency % from FetchSleep result."""
    if not sleep_data:
        return None
    # FetchSleep doesn't currently return efficiency directly — compute from durations
    # Efficiency = (total_sleep - awake) / total_sleep * 100
    # We can approximate: score 85+ ≈ 90%+ efficiency; use score as proxy if needed
    # Note: Garmin's sleep score is not the same as efficiency but correlates
    score = sleep_data.get("sleep_score", {})
    if isinstance(score, dict):
        return None  # score is quality label, not a percentage — skip for now
    return None
