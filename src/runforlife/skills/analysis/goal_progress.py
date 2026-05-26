"""
Race goal progress — bridges profile goals with current Garmin predictions.

The core question every athlete asks: "will I hit my goal?". This skill
fetches the current race prediction from Garmin and compares it to the
target time stored in the athlete's profile. Returns the gap, weeks
remaining, and whether the current trajectory is on track.
"""

from datetime import date
from typing import Any

from runforlife.skills.base import Skill
from runforlife.storage.profile_store import load_profile


def _parse_time_to_seconds(time_str: str) -> int | None:
    """Parse 'H:MM:SS' or 'MM:SS' to total seconds."""
    if not time_str:
        return None
    try:
        parts = time_str.strip().split(":")
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, IndexError):
        return None
    return None


def _format_gap(seconds: int) -> str:
    """Format a gap in seconds as '+M:SS' or '-M:SS'."""
    sign = "+" if seconds >= 0 else "-"
    abs_s = abs(seconds)
    m, s = divmod(abs_s, 60)
    return f"{sign}{m}:{s:02d}"


class GoalProgress(Skill):
    name = "goal_progress"

    description = (
        "Compare current Garmin race predictions against the athlete's HM goal time. "
        "Returns the gap to goal, weeks remaining to race, and whether current "
        "trajectory is on track. "
        "Use when the athlete asks 'am I on track for my goal?', 'will I hit 1:28?', "
        "'how close am I to my target?', 'how much do I need to improve?'."
    )

    input_schema = {
        "type": "object",
        "properties": {
            "user": {
                "type": "string",
                "enum": ["tezuesh", "kakul"],
                "description": "Which athlete",
            },
        },
        "required": ["user"],
    }

    def execute(self, **kwargs: Any) -> dict:
        user: str = kwargs["user"]

        profile = load_profile(user)
        hm_goal = profile["goals"]["half_marathon"]
        goal_time_str: str = hm_goal["target_time"]
        race_date_str: str = hm_goal["race_date"]

        # Weeks remaining
        today = date.today()
        race_date = date.fromisoformat(race_date_str)
        days_remaining = (race_date - today).days
        weeks_remaining = round(days_remaining / 7, 1)

        goal_secs = _parse_time_to_seconds(goal_time_str)
        if goal_secs is None:
            return {"success": False, "error": f"Could not parse goal time: {goal_time_str}"}

        # Fetch current race predictions from Garmin
        from runforlife.skills.data.fetch_race_predictions import FetchRacePredictions
        predictions_result = FetchRacePredictions().execute(user=user)

        if not predictions_result.get("success"):
            return {
                "success": False,
                "error": "Could not fetch race predictions from Garmin. Authenticate first.",
                "goal_time": goal_time_str,
                "race_date": race_date_str,
                "weeks_remaining": weeks_remaining,
            }

        # Extract half marathon prediction — key name may vary by Garmin response
        raw = predictions_result.get("predictions") or predictions_result
        hm_prediction_str = (
            raw.get("half_marathon")
            or raw.get("halfMarathon")
            or raw.get("21.1km")
        )

        if not hm_prediction_str:
            return {
                "success": True,
                "user": user,
                "goal_time": goal_time_str,
                "race_date": race_date_str,
                "weeks_remaining": weeks_remaining,
                "current_prediction": None,
                "gap_to_goal": None,
                "on_track": None,
                "note": "Garmin has no half marathon prediction yet — needs more running history.",
            }

        pred_secs = _parse_time_to_seconds(str(hm_prediction_str))
        if pred_secs is None:
            return {"success": False, "error": f"Could not parse prediction: {hm_prediction_str}"}

        gap_secs = pred_secs - goal_secs  # positive = slower than goal

        return {
            "success": True,
            "user": user,
            "goal_time": goal_time_str,
            "current_prediction": str(hm_prediction_str),
            "gap_to_goal": _format_gap(gap_secs),
            "gap_seconds": gap_secs,
            "on_track": gap_secs <= 0,
            "race_date": race_date_str,
            "weeks_remaining": weeks_remaining,
            "days_remaining": days_remaining,
        }
