from typing import Any

from runforlife.skills.base import Skill
from runforlife.skills.data.garmin_auth import get_session


class FetchGoals(Skill):
    name = "fetch_goals"

    description = (
        "Fetch training goals set in Garmin Connect for a user. "
        "Returns active, future, or past goals with progress toward each target. "
        "Use to understand what the user is working toward and how far they are. "
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
            "status": {
                "type": "string",
                "enum": ["active", "future", "past"],
                "description": "Goal status filter. Default: active",
            },
        },
        "required": ["user"],
    }

    def execute(self, **kwargs: Any) -> dict:
        user: str = kwargs["user"]
        status: str = kwargs.get("status", "active")

        try:
            garmin = get_session(user)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        try:
            goals = garmin.get_goals(status=status)
        except Exception as e:
            return {"success": False, "error": f"Failed to fetch goals: {e}"}

        parsed = [
            {
                "name": g.get("name") or g.get("goalTypeName"),
                "type": g.get("goalTypeKey"),
                "target": g.get("goalValue"),
                "current": g.get("currentValue"),
                "start_date": g.get("startDate"),
                "target_date": g.get("targetDate"),
                "completed": g.get("completed", False),
            }
            for g in (goals or [])
        ]

        return {
            "success": True,
            "user": user,
            "status": status,
            "goal_count": len(parsed),
            "goals": parsed,
        }
