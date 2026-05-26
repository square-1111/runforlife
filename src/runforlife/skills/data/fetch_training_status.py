from typing import Any

from runforlife.skills.base import Skill
from runforlife.skills.data.garmin_auth import get_session


class FetchTrainingStatus(Skill):
    name = "fetch_training_status"

    description = (
        "Fetch Garmin training status for a user on a given date. "
        "Status values: Productive, Maintaining, Recovery, Overreaching, Unproductive, Detraining. "
        "Also returns acute load (last 7 days), chronic load (last 28 days), and load ratio. "
        "Load ratio > 1.3 = overloading risk. Use to prevent overtraining. "
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
            data = garmin.get_training_status(date)
        except Exception as e:
            return {"success": False, "error": f"Failed to fetch training status: {e}"}

        # API returns nested or flat structure depending on date
        most_recent = data.get("mostRecentTrainingStatus") or {}
        if not most_recent and "trainingStatus" in data:
            most_recent = data

        status_key = (
            most_recent.get("trainingStatus")
            or most_recent.get("trainingStatusKey")
            or ""
        )

        return {
            "success": True,
            "user": user,
            "date": date,
            "status": status_key.replace("_", " ").title() if status_key else None,
            "acute_load": most_recent.get("acuteLoad") or most_recent.get("acuteTrainingLoad"),
            "chronic_load": most_recent.get("chronicLoad") or most_recent.get("chronicTrainingLoad"),
            "load_ratio": most_recent.get("loadRatio"),
            "load_balance": most_recent.get("loadBalance"),
        }
