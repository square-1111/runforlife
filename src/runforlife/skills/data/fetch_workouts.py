from typing import Any

from runforlife.skills.base import Skill
from runforlife.skills.data.garmin_auth import get_session


class FetchWorkouts(Skill):
    name = "fetch_workouts"

    description = (
        "Fetch saved workouts from Garmin Connect for a user. "
        "These are structured workouts (intervals, tempo, etc.) saved in the Garmin library. "
        "Returns workout names, sport types, estimated duration. "
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
            "limit": {
                "type": "integer",
                "description": "Max workouts to return. Default: 20",
            },
        },
        "required": ["user"],
    }

    def execute(self, **kwargs: Any) -> dict:
        user: str = kwargs["user"]
        limit: int = kwargs.get("limit", 20)

        try:
            garmin = get_session(user)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        try:
            workouts = garmin.get_workouts(start=0, limit=limit)
        except Exception as e:
            return {"success": False, "error": f"Failed to fetch workouts: {e}"}

        parsed = [
            {
                "id": w.get("workoutId"),
                "name": w.get("workoutName"),
                "sport": w.get("sportType", {}).get("sportTypeKey") if isinstance(w.get("sportType"), dict) else w.get("sportType"),
                "estimated_duration_min": round((w.get("estimatedDurationInSecs") or 0) / 60),
                "estimated_distance_km": round((w.get("estimatedDistanceInMeters") or 0) / 1000, 2),
            }
            for w in (workouts or [])
        ]

        return {
            "success": True,
            "user": user,
            "workout_count": len(parsed),
            "workouts": parsed,
        }
