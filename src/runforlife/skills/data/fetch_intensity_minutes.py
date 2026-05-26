from typing import Any

from runforlife.skills.base import Skill
from runforlife.skills.data.garmin_auth import get_session


class FetchIntensityMinutes(Skill):
    name = "fetch_intensity_minutes"

    description = (
        "Fetch weekly intensity minutes for a user. "
        "WHO recommends 150 moderate or 75 vigorous minutes per week. "
        "Returns moderate + vigorous actuals vs goals, and whether the WHO target was met. "
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
                "description": "Any date within the target week (YYYY-MM-DD)",
            },
        },
        "required": ["user", "date"],
    }

    def execute(self, **kwargs: Any) -> dict:
        user: str = kwargs["user"]
        date: str = kwargs["date"]

        try:
            garmin = get_session(user)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        try:
            data = garmin.get_intensity_minutes_data(date)
        except Exception as e:
            return {"success": False, "error": f"Failed to fetch intensity minutes: {e}"}

        moderate = data.get("weeklyModerateIntensityMinutes") or data.get("moderateIntensityMinutes")
        vigorous = data.get("weeklyVigorousIntensityMinutes") or data.get("vigorousIntensityMinutes")

        return {
            "success": True,
            "user": user,
            "date": date,
            "weekly_moderate_minutes": moderate,
            "weekly_vigorous_minutes": vigorous,
            "weekly_total_minutes": (moderate or 0) + (vigorous or 0),
            "weekly_goal_moderate": data.get("weeklyGoalModerateIntensityMinutes"),
            "weekly_goal_vigorous": data.get("weeklyGoalVigorousIntensityMinutes"),
            "who_goal_met": data.get("whoMinutesGoalMet"),
        }
