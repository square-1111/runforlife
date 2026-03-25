from typing import Any

from runforlife.skills.base import Skill
from runforlife.skills.data.garmin_auth import get_session


class FetchHRV(Skill):
    """Fetch Heart Rate Variability (HRV) data from Garmin Connect."""

    name = "fetch_hrv"

    description = (
        "Fetch Heart Rate Variability (HRV) data from Garmin Connect for a specific "
        "user and date. Returns last night average HRV, 5-minute high, baseline "
        "range values, and HRV status with human-readable interpretations. Use this "
        "to assess recovery, stress levels, and training readiness through HRV metrics. "
        "Requires garmin_auth to be called first."
    )

    input_schema = {
        "type": "object",
        "properties": {
            "user": {
                "type": "string",
                "enum": ["tezuesh", "kakul"],
                "description": "Which athlete to fetch HRV data for",
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
            hrv_data = garmin.get_hrv_data(date)
        except Exception as e:
            return {"success": False, "error": f"Failed to fetch HRV data: {e}"}

        # Extract HRV summary data
        hrv_summary = hrv_data.get("hrvSummary", {})
        
        if not hrv_summary:
            return {
                "success": True,
                "user": user,
                "date": date,
                "hrv_data": None,
                "summary": "No HRV data available for this date"
            }

        # Extract key HRV metrics
        last_night_avg = hrv_summary.get("lastNightAvg")
        last_night_5min_high = hrv_summary.get("lastNight5MinHigh")
        baseline = hrv_summary.get("baseline", {})
        status = hrv_summary.get("status")

        # Extract baseline range values
        baseline_low_upper = baseline.get("lowUpper")
        baseline_balanced_low = baseline.get("balancedLow")
        baseline_balanced_upper = baseline.get("balancedUpper")

        # Build clean response
        result = {
            "success": True,
            "user": user,
            "date": date,
            "hrv_data": {
                "last_night_average": last_night_avg,
                "last_night_5min_high": last_night_5min_high,
                "baseline_range": {
                    "low_upper": baseline_low_upper,
                    "balanced_low": baseline_balanced_low,
                    "balanced_upper": baseline_balanced_upper,
                },
                "status": status,
            },
        }

        # Create human-readable summary
        summary_parts = []
        
        if last_night_avg:
            summary_parts.append(f"Last Night Average HRV: {last_night_avg}ms")
        
        if last_night_5min_high:
            summary_parts.append(f"5-Min High: {last_night_5min_high}ms")
        
        if status:
            summary_parts.append(f"HRV Status: {status}")
        
        # Add baseline interpretation
        if baseline_balanced_low and baseline_balanced_upper:
            summary_parts.append(f"Baseline Balanced Range: {baseline_balanced_low}-{baseline_balanced_upper}ms")
        
        # Provide context if we have average and baseline
        if last_night_avg and baseline_balanced_low and baseline_balanced_upper:
            if last_night_avg >= baseline_balanced_low and last_night_avg <= baseline_balanced_upper:
                summary_parts.append("HRV within balanced range")
            elif last_night_avg > baseline_balanced_upper:
                summary_parts.append("HRV above balanced range")
            else:
                summary_parts.append("HRV below balanced range")

        result["summary"] = "; ".join(summary_parts) if summary_parts else "HRV data available but incomplete"

        return result