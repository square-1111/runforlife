"""
Pearson correlation between two stored metrics over a historical window.

Answers questions like:
  - "Does my sleep score predict my next-day readiness?"
  - "Is there a link between my HRV and my run pace?"
  - "Does running far increase my resting HR the next day?"

Reads directly from SQLite — exact numeric values, no embedding needed.
"""

from typing import Any
from datetime import date as date_cls

import numpy as np

from runforlife.skills.base import Skill
from runforlife.storage.metrics_store import get_window

AVAILABLE_METRICS = [
    "hrv_last_night",
    "resting_hr",
    "sleep_score",
    "readiness_score",
    "body_battery_end",
    "acwr",
    "run_distance_km",
    "hrv_7d_slope",
    "sleep_efficiency_delta",
]


def _pearson(x: list, y: list) -> float | None:
    pairs = [(a, b) for a, b in zip(x, y) if a is not None and b is not None]
    if len(pairs) < 5:
        return None
    xa = np.array([p[0] for p in pairs], dtype=float)
    ya = np.array([p[1] for p in pairs], dtype=float)
    if xa.std() == 0 or ya.std() == 0:
        return None
    return float(np.corrcoef(xa, ya)[0, 1])


def _interpret(r: float | None) -> str:
    if r is None:
        return "insufficient data"
    if abs(r) < 0.2:
        return "no meaningful relationship"
    if abs(r) < 0.4:
        return f"{'weak positive' if r > 0 else 'weak negative'} correlation"
    if abs(r) < 0.6:
        return f"{'moderate positive' if r > 0 else 'moderate negative'} correlation"
    return f"{'strong positive' if r > 0 else 'strong negative'} correlation"


class CorrelateMetrics(Skill):
    name = "correlate_metrics"

    description = (
        "Compute Pearson correlation between two stored metrics over a historical window. "
        "Use when the athlete asks 'does X affect Y' or 'is there a link between A and B'. "
        f"Available metrics: {', '.join(AVAILABLE_METRICS)}. "
        "Requires nightly sync history to have meaningful data. "
        "Returns correlation coefficient and plain-language interpretation."
    )

    input_schema = {
        "type": "object",
        "properties": {
            "user": {
                "type": "string",
                "enum": ["tezuesh", "kakul"],
                "description": "Which athlete",
            },
            "metric_x": {
                "type": "string",
                "enum": AVAILABLE_METRICS,
                "description": "First metric (independent variable)",
            },
            "metric_y": {
                "type": "string",
                "enum": AVAILABLE_METRICS,
                "description": "Second metric (dependent variable)",
            },
            "window_days": {
                "type": "integer",
                "description": "How many past days to include. Default: 90",
            },
            "end_date": {
                "type": "string",
                "description": "End date YYYY-MM-DD. Defaults to today.",
            },
        },
        "required": ["user", "metric_x", "metric_y"],
    }

    def execute(self, **kwargs: Any) -> dict:
        user: str = kwargs["user"]
        metric_x: str = kwargs["metric_x"]
        metric_y: str = kwargs["metric_y"]
        window_days: int = kwargs.get("window_days", 90)
        end_date: str = kwargs.get("end_date") or date_cls.today().isoformat()

        rows = get_window(user, end_date, window_days)

        x_series = [r.get(metric_x) for r in rows]
        y_series = [r.get(metric_y) for r in rows]

        r = _pearson(x_series, y_series)
        n_valid = sum(1 for a, b in zip(x_series, y_series) if a is not None and b is not None)

        return {
            "success": True,
            "user": user,
            "metric_x": metric_x,
            "metric_y": metric_y,
            "window_days": window_days,
            "n_data_points": n_valid,
            "pearson_r": round(r, 3) if r is not None else None,
            "interpretation": _interpret(r),
            "note": f"Based on {n_valid} days with both metrics present out of {len(rows)} days queried.",
        }
