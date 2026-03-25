from typing import Any

from runforlife.skills.base import Skill
from runforlife.skills.data.garmin_auth import get_session


class FetchVO2Max(Skill):
    """Fetch VO2 max and training metrics from Garmin Connect."""

    name = "fetch_vo2max"

    description = (
        "Fetch VO2 max value, fitness age, and training metrics from Garmin Connect "
        "for a specific user and date. Returns VO2 max data, fitness age, training "
        "load, training status, and other performance metrics in a clean format. "
        "Use this when you need to assess cardiorespiratory fitness and training "
        "readiness. Requires garmin_auth to be called first."
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
            # Fetch VO2 max and fitness metrics
            max_metrics = garmin.get_max_metrics(date)
            
            # Fetch training status and load
            training_status = garmin.get_training_status(date)
            
        except Exception as e:
            return {"success": False, "error": f"Failed to fetch VO2 max data: {e}"}

        # Extract VO2 max data from generic metrics
        generic_data = max_metrics.get("generic", {})
        vo2_max = generic_data.get("vo2MaxPreciseValue")
        fitness_age = generic_data.get("fitnessAge")
        vo2_max_running = generic_data.get("vo2MaxRunningPreciseValue")
        vo2_max_cycling = generic_data.get("vo2MaxCyclingPreciseValue")

        # Extract training status data
        training_load = training_status.get("trainingLoad")
        status_key = training_status.get("trainingStatusKey", "").replace("_", " ").title()
        load_focus = training_status.get("loadFocus")
        acute_load = training_status.get("acuteTrainingLoad")
        chronic_load = training_status.get("chronicTrainingLoad")

        # Build clean response
        result = {
            "success": True,
            "user": user,
            "date": date,
            "vo2_max": {
                "overall": vo2_max,
                "running": vo2_max_running,
                "cycling": vo2_max_cycling,
                "fitness_age": fitness_age,
            },
            "training_status": {
                "status": status_key,
                "training_load": training_load,
                "acute_load": acute_load,
                "chronic_load": chronic_load,
                "load_focus": load_focus,
            },
        }

        # Add summary for LLM
        summary_parts = []
        if vo2_max:
            summary_parts.append(f"VO2 Max: {vo2_max} ml/kg/min")
        if fitness_age:
            summary_parts.append(f"Fitness Age: {fitness_age} years")
        if status_key and status_key != "":
            summary_parts.append(f"Training Status: {status_key}")
        if training_load:
            summary_parts.append(f"Training Load: {training_load}")

        result["summary"] = "; ".join(summary_parts) if summary_parts else "No VO2 max data available for this date"

        return result