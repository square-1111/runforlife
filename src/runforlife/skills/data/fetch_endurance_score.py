from typing import Any

from runforlife.skills.base import Skill
from runforlife.skills.data.garmin_auth import get_session


class FetchEnduranceScore(Skill):
    name = "fetch_endurance_score"

    description = (
        "Fetch Garmin endurance score for a user. "
        "Reflects cumulative aerobic fitness from sustained efforts — distinct from VO2 max. "
        "Pass only date for a single-day score. Pass end_date too for weekly trend. "
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
            "end_date": {
                "type": "string",
                "description": "End date in YYYY-MM-DD (optional, returns weekly trend if provided)",
            },
        },
        "required": ["user", "date"],
    }

    def execute(self, **kwargs: Any) -> dict:
        user: str = kwargs["user"]
        date: str = kwargs["date"]
        end_date: str | None = kwargs.get("end_date")

        try:
            garmin = get_session(user)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        try:
            data = garmin.get_endurance_score(date, end_date)
        except Exception as e:
            return {"success": False, "error": f"Failed to fetch endurance score: {e}"}

        if end_date:
            return {
                "success": True,
                "user": user,
                "date_range": f"{date} to {end_date}",
                "weekly_trend": data if isinstance(data, list) else [data],
            }

        return {
            "success": True,
            "user": user,
            "date": date,
            "score": data.get("overallScore") or data.get("enduranceScore"),
            "level": data.get("scoreClassification") or data.get("tier"),
            "contribution_run": data.get("contributionFromRunActivities"),
            "contribution_cycling": data.get("contributionFromCyclingActivities"),
        }
