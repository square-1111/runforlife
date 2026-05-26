from typing import Any

from runforlife.skills.base import Skill
from runforlife.skills.data.garmin_auth import get_session


class FetchSteps(Skill):
    name = "fetch_steps"

    description = (
        "Fetch daily step count and optionally a weekly step summary for a user. "
        "Returns today's total steps and goal progress. "
        "Set weekly=true to get 12-week historical trend. "
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
            "date": {
                "type": "string",
                "description": "Date in YYYY-MM-DD format",
            },
            "weekly": {
                "type": "boolean",
                "description": "If true, also return 12-week step history ending on this date",
            },
        },
        "required": ["user", "date"],
    }

    def execute(self, **kwargs: Any) -> dict:
        user: str = kwargs["user"]
        date: str = kwargs["date"]
        weekly: bool = kwargs.get("weekly", False)

        try:
            garmin = get_session(user)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        result: dict = {"success": True, "user": user, "date": date}

        try:
            daily = garmin.get_steps_data(date)
            total_steps = sum(s.get("steps", 0) or 0 for s in (daily or []) if isinstance(s, dict))
            result["daily_steps"] = total_steps
        except Exception as e:
            result["daily_steps_error"] = str(e)

        if weekly:
            try:
                weekly_data = garmin.get_weekly_steps(date, weeks=12)
                result["weekly_history"] = [
                    {
                        "week_start": w.get("startDate"),
                        "total_steps": w.get("totalSteps"),
                        "avg_daily_steps": w.get("avgDailySteps"),
                        "daily_goal": w.get("dailyStepGoal"),
                    }
                    for w in (weekly_data or [])
                ]
            except Exception as e:
                result["weekly_history_error"] = str(e)

        return result
