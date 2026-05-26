"""
Weekly training summary — the most-called skill in any coaching session.

Aggregates a full week's metrics into a single response: runs, mileage,
avg HRV, sleep, readiness. Defaults to the current week (Mon–Sun).
"""

from datetime import date, timedelta
from typing import Any

from runforlife.skills.base import Skill
from runforlife.storage.metrics_store import get_window


def _avg(values: list) -> float | None:
    clean = [v for v in values if v is not None]
    return round(sum(clean) / len(clean), 1) if clean else None


def _monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


class WeeklySummary(Skill):
    name = "weekly_summary"

    description = (
        "Get a summary of training metrics for a full week. "
        "Returns total runs, total km, avg HRV, avg sleep score, avg readiness, "
        "avg body battery, and end-of-week ACWR. "
        "Use when the athlete asks 'how was my week?', 'what did I do this week?', "
        "'show me a weekly overview', or 'how has my recovery been this week?'. "
        "Defaults to the current week. Pass week_start (Monday YYYY-MM-DD) for any past week."
    )

    input_schema = {
        "type": "object",
        "properties": {
            "user": {
                "type": "string",
                "enum": ["tezuesh", "kakul"],
                "description": "Which athlete",
            },
            "week_start": {
                "type": "string",
                "description": "Monday of the target week (YYYY-MM-DD). Defaults to current week.",
            },
        },
        "required": ["user"],
    }

    def execute(self, **kwargs: Any) -> dict:
        user: str = kwargs["user"]
        week_start_str: str | None = kwargs.get("week_start")

        today = date.today()
        if week_start_str:
            week_start = date.fromisoformat(week_start_str)
        else:
            week_start = _monday_of(today)

        week_end = min(week_start + timedelta(days=6), today)
        week_end_str = week_end.isoformat()
        week_start_str = week_start.isoformat()

        # get_window returns up to 7 rows ending on week_end, oldest first
        all_rows = get_window(user, week_end_str, 7)
        rows = [r for r in all_rows if r["date"] >= week_start_str]

        if not rows:
            return {
                "success": True,
                "user": user,
                "week_start": week_start_str,
                "week_end": week_end_str,
                "days_with_data": 0,
                "note": "No data for this week. Run nightly sync to populate.",
            }

        run_rows = [r for r in rows if r.get("ran_today")]
        total_km = round(sum(r.get("run_distance_km") or 0 for r in run_rows), 1)

        return {
            "success": True,
            "user": user,
            "week_start": week_start_str,
            "week_end": week_end_str,
            "days_with_data": len(rows),
            "runs": len(run_rows),
            "total_km": total_km,
            "avg_hrv": _avg([r.get("hrv_last_night") for r in rows]),
            "avg_resting_hr": _avg([r.get("resting_hr") for r in rows]),
            "avg_sleep_score": _avg([r.get("sleep_score") for r in rows]),
            "avg_readiness": _avg([r.get("readiness_score") for r in rows]),
            "avg_body_battery_end": _avg([r.get("body_battery_end") for r in rows]),
            "acwr_end_of_week": rows[-1].get("acwr"),
            "hrv_7d_slope": rows[-1].get("hrv_7d_slope"),
        }
