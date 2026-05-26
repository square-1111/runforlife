from typing import Any

from runforlife.skills.base import Skill
from runforlife.skills.data.garmin_auth import get_session


class FetchHeartRate(Skill):
    name = "fetch_heart_rate"

    description = (
        "Fetch daily heart rate data for a user: resting HR, daily min/max/average. "
        "Resting HR trends downward as aerobic fitness improves — track it weekly. "
        "Also returns 7-day average resting HR for context. "
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
            hr_data = garmin.get_heart_rates(date)
        except Exception as e:
            return {"success": False, "error": f"Failed to fetch heart rate data: {e}"}

        rhr_value = None
        try:
            rhr_data = garmin.get_rhr_day(date)
            rhr_value = rhr_data.get("value") or rhr_data.get("restingHeartRate")
        except Exception:
            pass

        return {
            "success": True,
            "user": user,
            "date": date,
            "resting_hr": rhr_value,
            "min_hr": hr_data.get("minHeartRate"),
            "max_hr": hr_data.get("maxHeartRate"),
            "avg_hr": hr_data.get("averageHeartRate") or hr_data.get("averageWakingHeartRate"),
            "last_7_days_avg_rhr": hr_data.get("lastSevenDaysAvgRestingHeartRate"),
        }
