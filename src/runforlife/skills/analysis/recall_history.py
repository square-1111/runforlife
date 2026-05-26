"""
Retrieve historical daily metrics for pattern analysis.

Returns structured rows from SQLite so Claude can reason over exact
numbers to answer questions like:
  - "Last time my HRV was this low, what was my training load?"
  - "How was my recovery in the week before my last long run?"
  - "Show me weeks where I was overtrained"

Claude reads the rows and identifies patterns — more precise than
semantic similarity because it works on exact values.
"""

from typing import Any
from datetime import date as date_cls

from runforlife.skills.base import Skill
from runforlife.storage.metrics_store import get_window


class RecallHistory(Skill):
    name = "recall_history"

    description = (
        "Retrieve historical daily training metrics for pattern analysis. "
        "Use for questions about PAST episodes and trends: "
        "'last time HRV was low', 'weeks with high training load', "
        "'how was my recovery in April', 'when did I run well'. "
        "Returns structured rows with exact numbers you can reason over. "
        "For TODAY or YESTERDAY's data, use the live fetch_* skills instead."
    )

    input_schema = {
        "type": "object",
        "properties": {
            "user": {
                "type": "string",
                "enum": ["tezuesh", "kakul"],
                "description": "Which athlete",
            },
            "window_days": {
                "type": "integer",
                "description": "How many past days to look at. Default: 60",
            },
            "query_description": {
                "type": "string",
                "description": "What pattern you're looking for — shown in results for context.",
            },
            "filter_ran_only": {
                "type": "boolean",
                "description": "Only include days with a run",
            },
            "filter_acwr_above": {
                "type": "number",
                "description": "Only include days where ACWR exceeded this value",
            },
            "filter_hrv_below": {
                "type": "number",
                "description": "Only include days where HRV was below this value",
            },
        },
        "required": ["user"],
    }

    def execute(self, **kwargs: Any) -> dict:
        user: str = kwargs["user"]
        window_days: int = kwargs.get("window_days", 60)
        query_description: str = kwargs.get("query_description", "")
        filter_ran_only: bool = kwargs.get("filter_ran_only", False)
        filter_acwr_above: float | None = kwargs.get("filter_acwr_above")
        filter_hrv_below: float | None = kwargs.get("filter_hrv_below")

        end_date = date_cls.today().isoformat()
        rows = get_window(user, end_date, window_days)

        if filter_ran_only:
            rows = [r for r in rows if r.get("ran_today")]
        if filter_acwr_above is not None:
            rows = [r for r in rows if r.get("acwr") is not None and r["acwr"] > filter_acwr_above]
        if filter_hrv_below is not None:
            rows = [r for r in rows if r.get("hrv_last_night") is not None and r["hrv_last_night"] < filter_hrv_below]

        if not rows:
            return {
                "success": True,
                "user": user,
                "count": 0,
                "rows": [],
                "note": "No matching data. Run nightly sync to populate history.",
            }

        clean = [
            {
                "date": r["date"],
                "sleep_score": r.get("sleep_score"),
                "hrv": r.get("hrv_last_night"),
                "resting_hr": r.get("resting_hr"),
                "readiness": r.get("readiness_score"),
                "body_battery_end": r.get("body_battery_end"),
                "ran": bool(r.get("ran_today")),
                "run_km": r.get("run_distance_km"),
                "acwr": r.get("acwr"),
                "hrv_slope": r.get("hrv_7d_slope"),
                "sleep_delta": r.get("sleep_efficiency_delta"),
            }
            for r in rows
        ]

        return {
            "success": True,
            "user": user,
            "query_description": query_description,
            "window_days": window_days,
            "count": len(clean),
            "rows": clean,
        }
