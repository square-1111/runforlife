from typing import Any

from runforlife.skills.base import Skill
from runforlife.skills.data.garmin_auth import get_session


def _format_duration(seconds: float | None) -> str | None:
    if not seconds:
        return None
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


class FetchPersonalRecords(Skill):
    name = "fetch_personal_records"

    description = (
        "Fetch all-time personal records (PRs) from Garmin for a user. "
        "Returns fastest times for 1 mile, 5K, 10K, half marathon, marathon, and more. "
        "Use to track progress against bests and set new goals. "
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
            records = garmin.get_personal_record()
        except Exception as e:
            return {"success": False, "error": f"Failed to fetch personal records: {e}"}

        parsed = []
        if isinstance(records, list):
            for r in records:
                value_raw = r.get("value")
                parsed.append({
                    "type": r.get("typeKey") or r.get("activityType"),
                    "value": _format_duration(value_raw) if isinstance(value_raw, (int, float)) else value_raw,
                    "date": (r.get("activityStartDateTimeInGMT") or r.get("prStartTimeGmt") or "")[:10],
                    "activity_id": r.get("activityId"),
                })
        elif isinstance(records, dict):
            for key, val in records.items():
                if isinstance(val, dict):
                    value_raw = val.get("value")
                    parsed.append({
                        "type": key,
                        "value": _format_duration(value_raw) if isinstance(value_raw, (int, float)) else value_raw,
                        "date": (val.get("activityStartDateTimeInGMT") or "")[:10],
                        "activity_id": val.get("activityId"),
                    })

        return {
            "success": True,
            "user": user,
            "personal_records": parsed,
            "total_prs": len(parsed),
        }
