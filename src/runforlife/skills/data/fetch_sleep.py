from typing import Any

from runforlife.skills.base import Skill
from runforlife.skills.data.garmin_auth import get_session


class FetchSleep(Skill):
    """Fetch sleep data from Garmin Connect."""

    name = "fetch_sleep"

    description = (
        "Fetch detailed sleep data from Garmin Connect for a specific user and date. "
        "Returns total sleep duration, sleep stage breakdown (deep, light, REM, awake), "
        "sleep score with quality rating, and a comprehensive summary. "
        "Use this to analyze sleep patterns, quality, and recovery metrics. "
        "Requires garmin_auth to be called first."
    )

    input_schema = {
        "type": "object",
        "properties": {
            "user": {
                "type": "string",
                "enum": ["tezuesh", "kakul"],
                "description": "Which athlete to fetch sleep data for",
            },
            "date": {
                "type": "string",
                "description": "Date in YYYY-MM-DD format",
            },
        },
        "required": ["user", "date"],
    }

    def _seconds_to_duration(self, seconds: int) -> str:
        """Convert seconds to H:MM format."""
        if not seconds:
            return "0:00"
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}:{minutes:02d}"

    def execute(self, **kwargs: Any) -> dict:
        user: str = kwargs["user"]
        date: str = kwargs["date"]

        try:
            garmin = get_session(user)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        try:
            sleep_data = garmin.get_sleep_data(date)
        except Exception as e:
            return {"success": False, "error": f"Failed to fetch sleep data: {e}"}

        # Extract sleep data from the response
        daily_sleep = sleep_data.get("dailySleepDTO", {})
        
        if not daily_sleep:
            return {
                "success": True,
                "user": user,
                "date": date,
                "summary": "No sleep data available for this date"
            }

        # Extract sleep durations (in seconds)
        total_sleep = daily_sleep.get("sleepTimeSeconds", 0)
        deep_sleep = daily_sleep.get("deepSleepSeconds", 0)
        light_sleep = daily_sleep.get("lightSleepSeconds", 0)
        rem_sleep = daily_sleep.get("remSleepSeconds", 0)
        awake_time = daily_sleep.get("awakeSleepSeconds", 0)

        # Extract sleep score
        sleep_scores = daily_sleep.get("sleepScores", {})
        overall_score = sleep_scores.get("overall", {})
        score_value = overall_score.get("value")
        score_qualifier = overall_score.get("qualifierKey", "").replace("_", " ").title()

        # Build clean response with human-readable durations
        result = {
            "success": True,
            "user": user,
            "date": date,
            "sleep_duration": {
                "total": self._seconds_to_duration(total_sleep),
                "deep": self._seconds_to_duration(deep_sleep),
                "light": self._seconds_to_duration(light_sleep),
                "rem": self._seconds_to_duration(rem_sleep),
                "awake": self._seconds_to_duration(awake_time),
            },
            "sleep_score": {
                "value": score_value,
                "quality": score_qualifier,
            },
        }

        # Calculate percentages for summary
        if total_sleep > 0:
            deep_pct = round((deep_sleep / total_sleep) * 100, 1)
            light_pct = round((light_sleep / total_sleep) * 100, 1)
            rem_pct = round((rem_sleep / total_sleep) * 100, 1)
            awake_pct = round((awake_time / total_sleep) * 100, 1)
        else:
            deep_pct = light_pct = rem_pct = awake_pct = 0

        # Build comprehensive summary
        summary_parts = []
        if total_sleep:
            summary_parts.append(f"Total Sleep: {self._seconds_to_duration(total_sleep)}")
        if score_value:
            quality_text = f" ({score_qualifier})" if score_qualifier else ""
            summary_parts.append(f"Sleep Score: {score_value}{quality_text}")
        if deep_sleep:
            summary_parts.append(f"Deep: {self._seconds_to_duration(deep_sleep)} ({deep_pct}%)")
        if light_sleep:
            summary_parts.append(f"Light: {self._seconds_to_duration(light_sleep)} ({light_pct}%)")
        if rem_sleep:
            summary_parts.append(f"REM: {self._seconds_to_duration(rem_sleep)} ({rem_pct}%)")
        if awake_time:
            summary_parts.append(f"Awake: {self._seconds_to_duration(awake_time)} ({awake_pct}%)")

        result["summary"] = "; ".join(summary_parts) if summary_parts else "No detailed sleep data available for this date"

        return result