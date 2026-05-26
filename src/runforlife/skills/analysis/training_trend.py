"""
8-week rolling weekly training stats.

Answers "am I building consistently?", "show me my mileage trend",
"is my training load increasing?". Returns one row per week so Claude
can spot progression, regression, or inconsistency across training blocks.
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


class TrainingTrend(Skill):
    name = "training_trend"

    description = (
        "Show weekly training stats for the last N weeks — mileage, avg HRV, "
        "avg readiness, run count, and peak ACWR per week. "
        "Use when the athlete asks 'am I building fitness?', 'show me my mileage trend', "
        "'is my training consistent?', 'how has my load been over the last month?'. "
        "Returns one row per week, oldest to newest."
    )

    input_schema = {
        "type": "object",
        "properties": {
            "user": {
                "type": "string",
                "enum": ["tezuesh", "kakul"],
                "description": "Which athlete",
            },
            "weeks": {
                "type": "integer",
                "description": "Number of past weeks to include. Default: 8",
            },
        },
        "required": ["user"],
    }

    def execute(self, **kwargs: Any) -> dict:
        user: str = kwargs["user"]
        weeks: int = kwargs.get("weeks", 8)

        today = date.today()
        this_monday = _monday_of(today)

        weekly_rows = []
        for i in range(weeks - 1, -1, -1):
            week_start = this_monday - timedelta(weeks=i)
            week_end = min(week_start + timedelta(days=6), today)

            all_rows = get_window(user, week_end.isoformat(), 7)
            rows = [r for r in all_rows if r["date"] >= week_start.isoformat()]

            if not rows:
                continue

            run_rows = [r for r in rows if r.get("ran_today")]
            acwr_values = [r.get("acwr") for r in rows if r.get("acwr") is not None]

            weekly_rows.append({
                "week_start": week_start.isoformat(),
                "week_end": week_end.isoformat(),
                "days_with_data": len(rows),
                "runs": len(run_rows),
                "total_km": round(sum(r.get("run_distance_km") or 0 for r in run_rows), 1),
                "avg_hrv": _avg([r.get("hrv_last_night") for r in rows]),
                "avg_readiness": _avg([r.get("readiness_score") for r in rows]),
                "avg_sleep_score": _avg([r.get("sleep_score") for r in rows]),
                "peak_acwr": round(max(acwr_values), 2) if acwr_values else None,
            })

        return {
            "success": True,
            "user": user,
            "weeks_returned": len(weekly_rows),
            "weeks": weekly_rows,
        }
