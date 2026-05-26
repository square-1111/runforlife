from typing import Any

from runforlife.skills.base import Skill
from runforlife.skills.data.garmin_auth import get_session


class FetchBodyBattery(Skill):
    name = "fetch_body_battery"

    description = (
        "Fetch Garmin Body Battery energy levels for a user over a date range. "
        "Body Battery is 0-100: high = well-rested, low = fatigued. "
        "Returns daily charged/drained amounts and peak values. "
        "Use this to track recovery trends over multiple days. "
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
                "description": "End date in YYYY-MM-DD format (optional, defaults to start_date)",
            },
        },
        "required": ["user", "start_date"],
    }

    def execute(self, **kwargs: Any) -> dict:
        user: str = kwargs["user"]
        start_date: str = kwargs["start_date"]
        end_date: str = kwargs.get("end_date", start_date)

        try:
            garmin = get_session(user)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        try:
            data = garmin.get_body_battery(start_date, end_date)
        except Exception as e:
            return {"success": False, "error": f"Failed to fetch body battery: {e}"}

        if not data:
            return {
                "success": True,
                "user": user,
                "date_range": f"{start_date} to {end_date}",
                "days": [],
            }

        days = []
        for day in data:
            charged = day.get("charged") or 0
            drained = day.get("drained") or 0
            days.append({
                "date": day.get("calendarDate"),
                "highest_value": day.get("highestValue"),
                "lowest_value": day.get("lowestValue"),
                "charged": charged,
                "drained": drained,
                "net": charged - drained,
            })

        peak_values = [d["highest_value"] for d in days if d["highest_value"] is not None]
        return {
            "success": True,
            "user": user,
            "date_range": f"{start_date} to {end_date}",
            "avg_peak_battery": round(sum(peak_values) / len(peak_values), 1) if peak_values else None,
            "days": days,
        }
