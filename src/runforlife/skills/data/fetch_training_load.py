from typing import Any

from runforlife.skills.base import Skill
from runforlife.skills.data.garmin_auth import get_session


class FetchTrainingLoad(Skill):
    name = "fetch_training_load"

    description = (
        "Fetch running training load data — acute load (recent stress) vs chronic load (fitness base). "
        "Use to determine if training volume is building fitness or risking injury. "
        "Weekly aggregation shows trends; daily shows exact load per day. "
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
            "aggregation": {
                "type": "string",
                "enum": ["daily", "weekly"],
                "description": "Aggregation period. Default: weekly",
            },
        },
        "required": ["user", "start_date", "end_date"],
    }

    def execute(self, **kwargs: Any) -> dict:
        user: str = kwargs["user"]
        start_date: str = kwargs["start_date"]
        end_date: str = kwargs["end_date"]
        aggregation: str = kwargs.get("aggregation", "weekly")

        try:
            garmin = get_session(user)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        try:
            data = garmin.get_running_tolerance(start_date, end_date, aggregation)
        except Exception as e:
            return {"success": False, "error": f"Failed to fetch training load: {e}"}

        return {
            "success": True,
            "user": user,
            "date_range": f"{start_date} to {end_date}",
            "aggregation": aggregation,
            "data": data,
        }
