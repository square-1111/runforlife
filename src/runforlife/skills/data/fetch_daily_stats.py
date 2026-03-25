from typing import Any

from runforlife.skills.base import Skill
from runforlife.skills.data.garmin_auth import get_session


class FetchDailyStats(Skill):
    """Fetch daily statistics from Garmin Connect."""

    name = "fetch_daily_stats"

    description = (
        "Fetch daily statistics from Garmin Connect including steps, distance, "
        "heart rate metrics, stress levels, body battery, calories, and intensity "
        "minutes for a specific user and date. Returns comprehensive daily health "
        "and activity metrics in a clean, human-readable format. Use this to get "
        "a complete overview of someone's daily activity and wellness metrics. "
        "Requires garmin_auth to be called first."
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

    def _convert_meters_to_km(self, meters: float) -> float:
        """Convert meters to kilometers, rounded to 2 decimal places."""
        if meters is None:
            return 0.0
        return round(meters / 1000, 2)

    def execute(self, **kwargs: Any) -> dict:
        user: str = kwargs["user"]
        date: str = kwargs["date"]

        try:
            garmin = get_session(user)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        try:
            daily_stats = garmin.get_stats(date)
        except Exception as e:
            return {"success": False, "error": f"Failed to fetch daily stats: {e}"}

        if not daily_stats:
            return {
                "success": False,
                "error": "No daily stats data available for this date"
            }

        # Extract key metrics
        steps = daily_stats.get("totalSteps", 0)
        distance_meters = daily_stats.get("totalDistanceMeters", 0)
        distance_km = self._convert_meters_to_km(distance_meters)
        
        # Heart rate metrics
        resting_hr = daily_stats.get("restingHeartRate")
        max_hr = daily_stats.get("maxHeartRate")
        min_hr = daily_stats.get("minHeartRate")
        
        # Stress and body battery
        avg_stress = daily_stats.get("averageStressLevel")
        max_stress = daily_stats.get("maxStressLevel")
        body_battery_start = daily_stats.get("bodyBatteryChargedUp")
        body_battery_end = daily_stats.get("bodyBatteryDrained")
        body_battery_high = daily_stats.get("bodyBatteryHighestValue")
        body_battery_low = daily_stats.get("bodyBatteryLowestValue")
        
        # Calories
        total_calories = daily_stats.get("totalKilocalories")
        active_calories = daily_stats.get("activeKilocalories")
        resting_calories = daily_stats.get("bmrKilocalories")
        
        # Intensity minutes
        moderate_minutes = daily_stats.get("moderateIntensityMinutes", 0)
        vigorous_minutes = daily_stats.get("vigorousIntensityMinutes", 0)
        total_intensity_minutes = moderate_minutes + vigorous_minutes

        # Build clean response
        result = {
            "success": True,
            "user": user,
            "date": date,
            "steps": steps,
            "distance": {
                "total_km": distance_km,
                "total_meters": distance_meters,
            },
            "heart_rate": {
                "resting_bpm": resting_hr,
                "max_bpm": max_hr,
                "min_bpm": min_hr,
            },
            "stress": {
                "average_level": avg_stress,
                "max_level": max_stress,
            },
            "body_battery": {
                "start_of_day": body_battery_start,
                "end_of_day": body_battery_end,
                "highest_value": body_battery_high,
                "lowest_value": body_battery_low,
            },
            "calories": {
                "total": total_calories,
                "active": active_calories,
                "resting": resting_calories,
            },
            "intensity_minutes": {
                "moderate": moderate_minutes,
                "vigorous": vigorous_minutes,
                "total": total_intensity_minutes,
            },
        }

        # Create summary
        summary_parts = []
        if steps > 0:
            summary_parts.append(f"{steps:,} steps")
        if distance_km > 0:
            summary_parts.append(f"{distance_km} km distance")
        if resting_hr:
            summary_parts.append(f"RHR: {resting_hr} bpm")
        if max_hr:
            summary_parts.append(f"Max HR: {max_hr} bpm")
        if avg_stress:
            summary_parts.append(f"Avg stress: {avg_stress}")
        if body_battery_start and body_battery_end:
            bb_change = body_battery_end - body_battery_start
            summary_parts.append(f"Body battery: {body_battery_start}→{body_battery_end} ({bb_change:+d})")
        if total_calories:
            summary_parts.append(f"{total_calories} total calories")
        if total_intensity_minutes > 0:
            summary_parts.append(f"{total_intensity_minutes} intensity minutes")

        result["summary"] = "; ".join(summary_parts) if summary_parts else "Minimal activity data for this date"

        return result