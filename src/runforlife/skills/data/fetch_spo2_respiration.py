from typing import Any

from runforlife.skills.base import Skill
from runforlife.skills.data.garmin_auth import get_session


class FetchSpO2Respiration(Skill):
    name = "fetch_spo2_respiration"

    description = (
        "Fetch blood oxygen (SpO2) and breathing rate for a user on a given date. "
        "Normal SpO2: 95-100%. Normal resting breathing rate: 12-20 breaths/min. "
        "Low SpO2 or elevated breathing rate at rest can indicate poor recovery. "
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

        spo2 = None
        respiration = None

        try:
            spo2 = garmin.get_spo2_data(date)
        except Exception:
            pass

        try:
            respiration = garmin.get_respiration_data(date)
        except Exception:
            pass

        return {
            "success": True,
            "user": user,
            "date": date,
            "spo2": {
                "avg_pct": spo2.get("averageSpO2"),
                "lowest_pct": spo2.get("lowestSpO2"),
                "on_demand_reading": spo2.get("onDemandReading"),
            } if spo2 else None,
            "respiration": {
                "avg_waking_breaths_per_min": respiration.get("avgWakingRespirationValue"),
                "avg_sleep_breaths_per_min": respiration.get("avgSleepRespirationValue"),
                "highest_breaths_per_min": respiration.get("highestRespirationValue"),
                "lowest_breaths_per_min": respiration.get("lowestRespirationValue"),
            } if respiration else None,
        }
