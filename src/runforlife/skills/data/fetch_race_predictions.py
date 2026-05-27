from typing import Any

from runforlife.skills.base import Skill
from runforlife.skills.data.garmin_auth import get_session


class FetchRacePredictions(Skill):
    """Fetch race time predictions from Garmin Connect."""

    name = "fetch_race_predictions"

    description = (
        "Fetch race time predictions from Garmin Connect for a user. Returns "
        "predicted times for common race distances like 5K, 10K, half marathon, "
        "and marathon based on current fitness metrics. Times are converted to "
        "human-readable H:MM:SS format. Use this when you need to understand "
        "the athlete's current race performance potential or help set race goals. "
        "Requires garmin_auth to be called first."
    )

    input_schema = {
        "type": "object",
        "properties": {
            "user": {
                "type": "string",
                "enum": ["tezuesh", "kakul"],
                "description": "Which athlete to fetch predictions for",
            },
        },
        "required": ["user"],
    }

    def execute(self, **kwargs: Any) -> dict:
        user: str = kwargs["user"]

        try:
            garmin = get_session(user)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        try:
            predictions = garmin.get_race_predictions()
        except Exception as e:
            return {"success": False, "error": f"Failed to fetch race predictions: {e}"}

        if not predictions:
            return {"success": False, "error": "No race predictions available"}

        # Convert predictions to readable format
        formatted_predictions = {}
        distance_names = {
            5000: "5K",
            10000: "10K", 
            21097: "Half Marathon",
            42195: "Marathon"
        }

        def seconds_to_time(seconds):
            """Convert seconds to H:MM:SS format."""
            if not seconds:
                return "N/A"
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            secs = seconds % 60
            if hours > 0:
                return f"{hours}:{minutes:02d}:{secs:02d}"
            else:
                return f"{minutes}:{secs:02d}"

        # Garmin returns a flat dict: {time5K, time10K, timeHalfMarathon, timeMarathon}
        flat_keys = {
            "time5K": "5K",
            "time10K": "10K",
            "timeHalfMarathon": "Half Marathon",
            "timeMarathon": "Marathon",
        }
        if isinstance(predictions, dict):
            for key, race_name in flat_keys.items():
                time_s = predictions.get(key)
                if time_s:
                    formatted_predictions[race_name] = {
                        "time_seconds": time_s,
                        "time_formatted": seconds_to_time(time_s),
                    }
        else:
            # Fallback: list-of-dicts format
            for prediction in (predictions or []):
                if not isinstance(prediction, dict):
                    continue
                distance_m = prediction.get("raceDistanceInMeters")
                time_s = prediction.get("raceTimeinSeconds")
                if distance_m and time_s:
                    distance_km = distance_m / 1000
                    race_name = distance_names.get(distance_m, f"{distance_km:.1f}km")
                    formatted_predictions[race_name] = {
                        "distance_km": distance_km,
                        "time_seconds": time_s,
                        "time_formatted": seconds_to_time(time_s),
                    }

        # Create summary for common distances
        summary_parts = []
        for race in ["5K", "10K", "Half Marathon", "Marathon"]:
            if race in formatted_predictions:
                time_str = formatted_predictions[race]["time_formatted"]
                summary_parts.append(f"{race}: {time_str}")

        return {
            "success": True,
            "user": user,
            "predictions": formatted_predictions,
            "summary": ", ".join(summary_parts) if summary_parts else "No race predictions available",
            "total_predictions": len(formatted_predictions)
        }