from typing import Any

from runforlife.skills.base import Skill
from runforlife.skills.data.garmin_auth import get_session


def _classify_stress(level: int | None) -> str:
    if level is None:
        return "unknown"
    if level <= 25:
        return "resting"
    if level <= 50:
        return "low"
    if level <= 75:
        return "medium"
    return "high"


class FetchStress(Skill):
    name = "fetch_stress"

    description = (
        "Fetch daily stress levels from Garmin for a user. "
        "Stress is 0-100: ≤25=resting, 26-50=low, 51-75=medium, 76+=high. "
        "Returns average stress, peak stress, and time spent in each zone. "
        "Use to understand recovery quality and life stress load. "
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
            data = garmin.get_stress_data(date)
        except Exception as e:
            return {"success": False, "error": f"Failed to fetch stress data: {e}"}

        avg_stress = data.get("avgStressLevel")
        max_stress = data.get("maxStressLevel")

        return {
            "success": True,
            "user": user,
            "date": date,
            "avg_stress": avg_stress,
            "avg_stress_level": _classify_stress(avg_stress),
            "peak_stress": max_stress,
            "stress_duration_minutes": {
                "rest": data.get("restStressDuration"),
                "low": data.get("lowStressDuration"),
                "medium": data.get("mediumStressDuration"),
                "high": data.get("highStressDuration"),
            },
        }
