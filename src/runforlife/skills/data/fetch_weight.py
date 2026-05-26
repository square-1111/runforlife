from typing import Any

from runforlife.skills.base import Skill
from runforlife.skills.data.garmin_auth import get_session


class FetchWeight(Skill):
    name = "fetch_weight"

    description = (
        "Fetch weight check-ins and body composition data over a date range for a user. "
        "Returns each weigh-in with weight in kg and BMI. "
        "Use to track weight trends over time and correlate with training load. "
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
        },
        "required": ["user", "start_date", "end_date"],
    }

    def execute(self, **kwargs: Any) -> dict:
        user: str = kwargs["user"]
        start_date: str = kwargs["start_date"]
        end_date: str = kwargs["end_date"]

        try:
            garmin = get_session(user)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        try:
            data = garmin.get_weigh_ins(start_date, end_date)
        except Exception as e:
            return {"success": False, "error": f"Failed to fetch weight data: {e}"}

        raw = data.get("dailyWeightSummaries") or data.get("weightSummaries") or []
        entries = []
        for day in raw:
            summary = day.get("summaryDTO") or day
            weight_g = summary.get("weight") or summary.get("weightInGrams")
            if weight_g:
                entries.append({
                    "date": summary.get("calendarDate"),
                    "weight_kg": round(weight_g / 1000, 1),
                    "bmi": summary.get("bmi"),
                })

        weights = [e["weight_kg"] for e in entries]
        return {
            "success": True,
            "user": user,
            "date_range": f"{start_date} to {end_date}",
            "entries": entries,
            "latest_weight_kg": entries[-1]["weight_kg"] if entries else None,
            "avg_weight_kg": round(sum(weights) / len(weights), 1) if weights else None,
            "change_kg": round(entries[-1]["weight_kg"] - entries[0]["weight_kg"], 1) if len(entries) >= 2 else None,
        }
