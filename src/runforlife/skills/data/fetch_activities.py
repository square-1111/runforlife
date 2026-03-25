"""
SKILL: fetch_activities
========================
The most important data skill — almost everything else depends on it.

DESIGN LESSON: Notice how this skill IMPORTS from garmin_auth (get_session).
Skills can depend on each other at the code level. But the LLM doesn't know
or care about Python imports. The LLM figures out the dependency order from
natural language — garmin_auth's description says "call this BEFORE any other
Garmin data skill."

Good descriptions > clever code architecture.

DESIGN LESSON: We return a SUMMARY alongside the raw data.
LLMs are bad at counting and arithmetic. If we return 30 activities,
the LLM might miscount totals. So we pre-compute the summary.
Rule of thumb: do math in code, do reasoning in the LLM.
"""

from typing import Any

from runforlife.skills.base import Skill
from runforlife.skills.data.garmin_auth import get_session

ACTIVITY_TYPE_MAP = {
    "running": ["running", "trail_running", "treadmill_running"],
    "walking": ["walking", "hiking"],
    "strength": ["strength_training", "other"],
    "cycling": ["cycling", "indoor_cycling"],
}


def _format_pace(speed_mps: float | None) -> str | None:
    """Convert m/s to min:sec/km."""
    if not speed_mps or speed_mps <= 0:
        return None
    pace_seconds = 1000 / speed_mps
    minutes = int(pace_seconds // 60)
    seconds = int(pace_seconds % 60)
    return f"{minutes}:{seconds:02d}/km"


def _format_duration(seconds: float | None) -> str | None:
    """Convert seconds to H:MM:SS or MM:SS."""
    if not seconds:
        return None
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _parse_activity(raw: dict) -> dict:
    """
    Transform Garmin's raw activity into a clean, LLM-friendly format.

    Garmin returns 100+ fields with names like "averageSpeed" (in m/s).
    We extract what matters and convert to human-readable formats so the
    LLM can say "your pace was 5:32/km" instead of doing float math.
    """
    distance_km = round((raw.get("distance", 0) or 0) / 1000, 2)
    duration_sec = raw.get("duration", 0) or 0

    return {
        "id": raw.get("activityId"),
        "name": raw.get("activityName", "Untitled"),
        "type": raw.get("activityType", {}).get("typeKey", "unknown"),
        "date": raw.get("startTimeLocal", "")[:10],
        "start_time": raw.get("startTimeLocal", ""),
        "distance_km": distance_km,
        "duration": _format_duration(duration_sec),
        "duration_seconds": int(duration_sec),
        "avg_pace": _format_pace(raw.get("averageSpeed")),
        "avg_hr": int(raw["averageHR"]) if raw.get("averageHR") else None,
        "max_hr": int(raw["maxHR"]) if raw.get("maxHR") else None,
        "calories": raw.get("calories"),
        "avg_cadence": raw.get("averageRunningCadenceInStepsPerMinute"),
        "elevation_gain": raw.get("elevationGain"),
        "training_effect_aerobic": raw.get("aerobicTrainingEffect"),
        "training_effect_anaerobic": raw.get("anaerobicTrainingEffect"),
    }


class FetchActivities(Skill):
    """Fetch activities from Garmin Connect."""

    name = "fetch_activities"

    description = (
        "Fetch running and workout activities from Garmin Connect for a specific "
        "user and date range. Returns a list of activities with distance, duration, "
        "pace, heart rate, and calories. Also returns pre-computed summary stats. "
        "Use this when you need to know what training someone has done. "
        "Requires garmin_auth to be called first."
    )

    input_schema = {
        "type": "object",
        "properties": {
            "user": {
                "type": "string",
                "enum": ["tezuesh", "kakul"],
                "description": "Which athlete to fetch data for",
            },
            "start_date": {
                "type": "string",
                "description": "Start date in YYYY-MM-DD format",
            },
            "end_date": {
                "type": "string",
                "description": "End date in YYYY-MM-DD format",
            },
            "activity_type": {
                "type": "string",
                "enum": ["running", "walking", "strength", "cycling", "all"],
                "description": "Filter by activity type. Defaults to 'all'",
            },
        },
        "required": ["user", "start_date", "end_date"],
    }

    def execute(self, **kwargs: Any) -> dict:
        user: str = kwargs["user"]
        start_date: str = kwargs["start_date"]
        end_date: str = kwargs["end_date"]
        activity_type: str = kwargs.get("activity_type", "all")

        try:
            garmin = get_session(user)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        try:
            raw_activities = garmin.get_activities_by_date(start_date, end_date)
        except Exception as e:
            return {"success": False, "error": f"Failed to fetch: {e}"}

        # Filter by type
        if activity_type != "all" and activity_type in ACTIVITY_TYPE_MAP:
            allowed = ACTIVITY_TYPE_MAP[activity_type]
            raw_activities = [
                a for a in raw_activities
                if a.get("activityType", {}).get("typeKey", "") in allowed
            ]

        activities = sorted(
            [_parse_activity(a) for a in raw_activities],
            key=lambda a: a["date"],
        )

        # Pre-computed summary — don't make the LLM do math
        total_distance = round(sum(a["distance_km"] for a in activities), 2)
        total_duration_sec = sum(a["duration_seconds"] for a in activities)
        run_count = len([a for a in activities if "running" in a["type"]])

        return {
            "success": True,
            "user": user,
            "date_range": f"{start_date} to {end_date}",
            "activity_count": len(activities),
            "run_count": run_count,
            "total_distance_km": total_distance,
            "total_duration": _format_duration(total_duration_sec),
            "activities": activities,
        }
