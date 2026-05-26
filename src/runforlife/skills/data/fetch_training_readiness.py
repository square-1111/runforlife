from typing import Any

from runforlife.skills.base import Skill
from runforlife.skills.data.garmin_auth import get_session


def _extract_readiness(r: dict | list | None) -> dict | None:
    if not r:
        return None
    if isinstance(r, list):
        r = r[0] if r else None
    if not r:
        return None
    return {
        "score": r.get("score") or r.get("readinessScore"),
        "level": r.get("scoreQualifier") or r.get("scoreClassification"),
        "sleep_score": r.get("sleepScore"),
        "hrv_status": r.get("hrvStatus"),
        "recovery_time_hours": r.get("recoveryTime"),
        "acwrFeedback": r.get("acwrFeedback"),
    }


class FetchTrainingReadiness(Skill):
    name = "fetch_training_readiness"

    description = (
        "Fetch Garmin training readiness score (0-100) for a user. "
        "Combines sleep quality, HRV status, recovery time, and training load. "
        "Score ≥75 = ready to train hard; 50-74 = moderate workout; <50 = rest or easy. "
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

        readiness = None
        morning = None

        try:
            readiness = garmin.get_training_readiness(date)
        except Exception:
            pass

        try:
            morning = garmin.get_morning_training_readiness(date)
        except Exception:
            pass

        if readiness is None and morning is None:
            return {"success": False, "user": user, "error": "No training readiness data available"}

        return {
            "success": True,
            "user": user,
            "date": date,
            "readiness": _extract_readiness(readiness),
            "morning_readiness": _extract_readiness(morning),
        }
