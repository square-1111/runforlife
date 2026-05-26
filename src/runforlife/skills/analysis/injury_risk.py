"""
Multi-signal injury risk assessment.

Combines three independent risk signals into a composite score:
  1. ACWR (Acute:Chronic Workload Ratio) — workload spike detection
  2. HRV 7-day slope — recovery stress accumulation
  3. Sleep quality delta — systemic fatigue signal

Risk levels:
  LOW      — all signals safe, proceed as planned
  MODERATE — 1 signal flagged, consider reducing intensity
  HIGH     — 2 signals flagged, recommend easy session or rest
  CRITICAL — 3 signals flagged, recommend rest day

Reads from the SQLite metrics table — requires nightly sync to have run.
"""

from typing import Any

from runforlife.config import ACWR_HIGH_RISK, ACWR_SAFE_MAX, HRV_SLOPE_WARNING
from runforlife.skills.base import Skill
from runforlife.storage.metrics_store import get_day, has_day


def _risk_level(flags: int) -> str:
    return {0: "low", 1: "moderate", 2: "high", 3: "critical"}.get(flags, "high")


class InjuryRisk(Skill):
    name = "injury_risk"

    description = (
        "Compute a multi-signal injury risk score from stored historical data. "
        "Combines ACWR (workload ratio), HRV 7-day trend, and sleep quality delta. "
        "Use proactively when the athlete asks about training load, recovery, or "
        "'should I do a hard session today?' "
        "Returns risk level (low/moderate/high/critical) with specific flags. "
        "Requires nightly sync to have run for accurate results."
    )

    input_schema = {
        "type": "object",
        "properties": {
            "user": {
                "type": "string",
                "enum": ["tezuesh", "kakul"],
                "description": "Which athlete to assess",
            },
            "date": {
                "type": "string",
                "description": "Date to assess (YYYY-MM-DD). Defaults to most recent synced day.",
            },
        },
        "required": ["user"],
    }

    def execute(self, **kwargs: Any) -> dict:
        user: str = kwargs["user"]
        date: str | None = kwargs.get("date")

        if date is None:
            from datetime import date as date_cls, timedelta
            for i in range(7):
                candidate = (date_cls.today() - timedelta(days=i)).isoformat()
                if has_day(user, candidate):
                    date = candidate
                    break
            if date is None:
                return {
                    "success": False,
                    "error": "No synced data found. Run: uv run python -m runforlife.sync.nightly --user " + user,
                }

        row = get_day(user, date)
        if not row:
            return {
                "success": False,
                "date": date,
                "error": f"No data for {date}. Run nightly sync first.",
            }

        acwr = row.get("acwr")
        hrv_slope = row.get("hrv_7d_slope")
        sleep_delta = row.get("sleep_efficiency_delta")

        flags = []
        details = []

        if acwr is not None:
            if acwr > ACWR_HIGH_RISK:
                flags.append("acwr_critical")
                details.append(f"ACWR {acwr:.2f} is above {ACWR_HIGH_RISK} (high injury risk zone)")
            elif acwr > ACWR_SAFE_MAX:
                flags.append("acwr_elevated")
                details.append(f"ACWR {acwr:.2f} is above safe zone {ACWR_SAFE_MAX}")
        else:
            details.append("ACWR: not available (needs more data)")

        if hrv_slope is not None:
            if hrv_slope < HRV_SLOPE_WARNING:
                flags.append("hrv_declining")
                details.append(f"HRV declining at {hrv_slope:+.1f}ms/day over 7 days")
        else:
            details.append("HRV trend: not available")

        if sleep_delta is not None:
            if sleep_delta < -10:
                flags.append("sleep_degraded")
                details.append(f"Sleep quality {sleep_delta:+.0f} points below 28-day baseline")
        else:
            details.append("Sleep delta: not available (needs more history)")

        risk = _risk_level(len(flags))

        recommendation = {
            "low": "Training load is appropriate. Proceed with planned session.",
            "moderate": "One risk signal active. Reduce intensity if feeling off; monitor tomorrow.",
            "high": "Two risk signals active. Recommend easy aerobic session only (Z1-Z2).",
            "critical": "All risk signals active. Rest day strongly recommended.",
        }[risk]

        return {
            "success": True,
            "user": user,
            "date": date,
            "risk_level": risk,
            "flags": flags,
            "details": details,
            "recommendation": recommendation,
            "metrics": {
                "acwr": acwr,
                "hrv_7d_slope": hrv_slope,
                "sleep_efficiency_delta": sleep_delta,
                "readiness_score": row.get("readiness_score"),
                "hrv_last_night": row.get("hrv_last_night"),
            },
        }
