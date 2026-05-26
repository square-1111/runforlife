from typing import Any

from runforlife.skills.base import Skill
from runforlife.skills.data.garmin_auth import get_session


class FetchProgressSummary(Skill):
    name = "fetch_progress_summary"

    description = (
        "Fetch aggregated fitness progress between two dates for a user. "
        "Groups totals by activity type (running, cycling, etc). "
        "Metric options: 'distance', 'duration', 'elevationGain', 'movingDuration'. "
        "Use to summarize a training block or month-over-month comparisons. "
        "Requires garmin_auth first."
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
            "metric": {
                "type": "string",
                "enum": ["distance", "duration", "elevationGain", "movingDuration"],
                "description": "Which metric to aggregate. Default: distance",
            },
        },
        "required": ["user", "start_date", "end_date"],
    }

    def execute(self, **kwargs: Any) -> dict:
        user: str = kwargs["user"]
        start_date: str = kwargs["start_date"]
        end_date: str = kwargs["end_date"]
        metric: str = kwargs.get("metric", "distance")

        try:
            garmin = get_session(user)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        try:
            data = garmin.get_progress_summary_between_dates(
                start_date, end_date, metric=metric, groupbyactivities=True
            )
        except Exception as e:
            return {"success": False, "error": f"Failed to fetch progress summary: {e}"}

        return {
            "success": True,
            "user": user,
            "date_range": f"{start_date} to {end_date}",
            "metric": metric,
            "by_activity_type": data,
        }
