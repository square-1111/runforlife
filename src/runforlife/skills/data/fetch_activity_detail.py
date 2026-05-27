from typing import Any

from runforlife.skills.base import Skill
from runforlife.skills.data.garmin_auth import get_session


def _format_pace(speed_mps: float | None) -> str | None:
    if not speed_mps or speed_mps <= 0:
        return None
    pace_sec = 1000 / speed_mps
    return f"{int(pace_sec // 60)}:{int(pace_sec % 60):02d}/km"


def _format_duration(seconds: float | None) -> str | None:
    if not seconds:
        return None
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


class FetchActivityDetail(Skill):
    name = "fetch_activity_detail"

    description = (
        "Fetch detailed data for a specific activity by ID: splits/laps, "
        "per-lap pace, HR, training effect, and HR zone distribution (% time in Z1-Z5). "
        "Use for deep-dive analysis of one specific run — especially to verify Zone 2 compliance "
        "(was this actually a Z2 run or did it drift into Z3?). "
        "Get the activity_id from fetch_activities results. "
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
            "activity_id": {
                "type": "string",
                "description": "Activity ID from fetch_activities results",
            },
        },
        "required": ["user", "activity_id"],
    }

    def execute(self, **kwargs: Any) -> dict:
        user: str = kwargs["user"]
        activity_id: str = str(kwargs["activity_id"])

        try:
            garmin = get_session(user)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        try:
            activity = garmin.get_activity(activity_id)
        except Exception as e:
            return {"success": False, "error": f"Failed to fetch activity: {e}"}

        splits = []
        try:
            splits_raw = garmin.get_activity_split_summaries(activity_id)
            lap_list = []
            if isinstance(splits_raw, dict):
                lap_list = splits_raw.get("lapDTOs") or splits_raw.get("splitSummaries") or []
            for i, lap in enumerate(lap_list[:20]):
                splits.append({
                    "lap": i + 1,
                    "distance_km": round((lap.get("distance") or 0) / 1000, 2),
                    "duration": _format_duration(lap.get("duration")),
                    "avg_pace": _format_pace(lap.get("averageSpeed")),
                    "avg_hr": lap.get("averageHR"),
                    "elevation_gain": lap.get("elevationGain"),
                })
        except Exception:
            pass

        hr_zones = []
        try:
            zones_raw = garmin.get_activity_hr_in_timezones(activity_id)
            total_secs = sum(z.get("secsInZone", 0) for z in (zones_raw or []))
            for z in (zones_raw or []):
                secs = z.get("secsInZone", 0)
                hr_zones.append({
                    "zone": z.get("zoneNumber"),
                    "min_hr": z.get("zoneLowBoundary"),
                    "seconds": round(secs),
                    "minutes": round(secs / 60, 1),
                    "pct": round(secs / total_secs * 100, 1) if total_secs else 0,
                })
        except Exception:
            pass

        return {
            "success": True,
            "user": user,
            "activity_id": activity_id,
            "name": activity.get("activityName"),
            "type": activity.get("activityType", {}).get("typeKey"),
            "date": (activity.get("startTimeLocal") or "")[:10],
            "distance_km": round((activity.get("distance") or 0) / 1000, 2),
            "duration": _format_duration(activity.get("duration")),
            "avg_pace": _format_pace(activity.get("averageSpeed")),
            "avg_hr": activity.get("averageHR"),
            "max_hr": activity.get("maxHR"),
            "aerobic_te": activity.get("aerobicTrainingEffect"),
            "anaerobic_te": activity.get("anaerobicTrainingEffect"),
            "calories": activity.get("calories"),
            "elevation_gain": activity.get("elevationGain"),
            "splits": splits,
            "hr_zones": hr_zones,
        }
