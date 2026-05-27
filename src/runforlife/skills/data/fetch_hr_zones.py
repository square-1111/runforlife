from typing import Any

from runforlife.skills.base import Skill
from runforlife.skills.data.garmin_auth import get_session


class FetchHRZones(Skill):
    """Fetch the athlete's configured heart rate zones from Garmin."""

    name = "fetch_hr_zones"

    description = (
        "Fetch the athlete's heart rate zone boundaries (Z1–Z5) from Garmin. "
        "Returns each zone's lower HR boundary and the HR range for each zone. "
        "Use this when you need to know the athlete's specific zone definitions "
        "before analyzing whether their runs were truly Zone 2, Zone 3, etc. "
        "Requires garmin_auth first."
    )

    input_schema = {
        "type": "object",
        "properties": {
            "user": {
                "type": "string",
                "enum": ["tezuesh", "kakul"],
                "description": "Which athlete",
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

        # Get a recent activity to read zone boundaries from
        try:
            recent = garmin.get_activities(0, 1)
        except Exception as e:
            return {"success": False, "error": f"Could not fetch recent activity: {e}"}

        if not recent:
            return {"success": False, "error": "No activities found to derive zone boundaries"}

        activity_id = recent[0].get("activityId")
        try:
            zones_raw = garmin.get_activity_hr_in_timezones(activity_id)
        except Exception as e:
            return {"success": False, "error": f"Could not fetch HR zones: {e}"}

        if not zones_raw:
            return {"success": False, "error": "No HR zone data returned"}

        boundaries = sorted(zones_raw, key=lambda z: z.get("zoneNumber", 0))
        zones = []
        for i, z in enumerate(boundaries):
            low = z.get("zoneLowBoundary")
            next_z = boundaries[i + 1] if i + 1 < len(boundaries) else None
            high = (next_z.get("zoneLowBoundary") - 1) if next_z else None
            zones.append({
                "zone": z.get("zoneNumber"),
                "low_bpm": low,
                "high_bpm": high,
                "range": f"{low}–{high} bpm" if high else f"{low}+ bpm",
            })

        return {
            "success": True,
            "user": user,
            "zones": zones,
            "summary": ", ".join(f"Z{z['zone']}: {z['range']}" for z in zones),
        }
