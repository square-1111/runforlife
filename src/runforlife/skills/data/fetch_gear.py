from typing import Any

from runforlife.skills.base import Skill
from runforlife.skills.data.garmin_auth import get_session


class FetchGear(Skill):
    name = "fetch_gear"

    description = (
        "Fetch running gear (shoes and equipment) registered in Garmin Connect for a user. "
        "Returns each item with total activities, total distance in km. "
        "Useful for tracking shoe mileage — replace shoes every ~800 km to avoid injury. "
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
            profile = garmin.get_userprofile_settings()
            profile_number = str(profile.get("userData", {}).get("userProfilePk") or "")
        except Exception as e:
            return {"success": False, "error": f"Failed to fetch user profile: {e}"}

        if not profile_number:
            return {"success": False, "error": "Could not retrieve user profile number for gear lookup"}

        try:
            gear_list = garmin.get_gear(profile_number)
        except Exception as e:
            return {"success": False, "error": f"Failed to fetch gear: {e}"}

        gear = []
        for item in (gear_list if isinstance(gear_list, list) else []):
            total_dist_m = item.get("totalDistance") or 0
            gear.append({
                "name": item.get("displayName") or item.get("customMakeModel"),
                "type": item.get("gearTypeName"),
                "uuid": item.get("uuid"),
                "active": item.get("gearStatusName") == "active",
                "total_activities": item.get("totalActivities"),
                "total_distance_km": round(total_dist_m / 1000, 1),
                "model": item.get("customMakeModel"),
            })

        return {
            "success": True,
            "user": user,
            "gear_count": len(gear),
            "gear": gear,
        }
