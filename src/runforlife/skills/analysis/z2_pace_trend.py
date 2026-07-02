"""
Zone-2 aerobic-progress trend.

Answers the base-builder's core question — "is my easy/Z2 pace getting faster at
the same heart rate?" — which raw pace cannot answer when effort is held down in
the base phase. Uses Efficiency Factor (speed/HR) and pace normalised to a fixed
reference HR, split by indoor vs outdoor because treadmill pace is set (not
GPS-measured) and trends separately from outdoor pace. Returns numbers; the coach
narrates.
"""

from datetime import date
from typing import Any

from runforlife.rag.features import efficiency_factor, linear_slope
from runforlife.skills.base import Skill
from runforlife.storage.metrics_store import get_window


def _fmt_pace(sec_per_km: float | None) -> str | None:
    if not sec_per_km or sec_per_km <= 0:
        return None
    m, s = divmod(round(sec_per_km), 60)
    return f"{m}:{s:02d}"


def _pace_at_ref_hr(ef: float | None, ref_hr: int) -> float | None:
    """Invert EF (m/min ÷ HR) to the pace (sec/km) the athlete would run at ref_hr."""
    if not ef or ef <= 0:
        return None
    meters_per_min = ef * ref_hr
    return round(60000.0 / meters_per_min, 1)


def _summarise(runs: list[dict], ref_hr: int) -> dict:
    """Trend stats for one bucket of Z2 runs (chronological)."""
    efs = [r["ef"] for r in runs if r["ef"] is not None]
    slope = linear_slope(efs) if len(efs) >= 3 else None
    ef_first = efs[0] if efs else None
    ef_last = efs[-1] if efs else None
    return {
        "n": len(runs),
        "ef_slope_per_run": round(slope, 4) if slope is not None else None,
        "ef_first": ef_first,
        "ef_last": ef_last,
        "pace_at_ref_first": _fmt_pace(_pace_at_ref_hr(ef_first, ref_hr)),
        "pace_at_ref_last": _fmt_pace(_pace_at_ref_hr(ef_last, ref_hr)),
        "runs": runs,
    }


class Z2PaceTrend(Skill):
    name = "z2_pace_trend"

    description = (
        "Aerobic-progress trend for easy/Zone-2 runs: is the athlete getting faster "
        "at the same heart rate? Uses Efficiency Factor (speed/HR) and pace normalised "
        "to a reference HR, split into indoor (treadmill) vs outdoor because treadmill "
        "pace is set, not GPS-measured, and trends separately. Use when the athlete asks "
        "'is my Z2 pace improving?', 'am I getting fitter?', 'is my easy pace dropping?', "
        "'how's my aerobic base?'."
    )

    input_schema = {
        "type": "object",
        "properties": {
            "user": {"type": "string", "enum": ["tezuesh", "kakul"], "description": "Which athlete"},
            "weeks": {"type": "integer", "description": "Lookback window in weeks. Default 8."},
            "hr_low": {"type": "integer", "description": "Bottom of the Z2 HR band. Default 125."},
            "hr_high": {"type": "integer", "description": "Top of the Z2 HR band. Default 145."},
        },
        "required": ["user"],
    }

    def execute(self, **kwargs: Any) -> dict:
        user: str = kwargs["user"]
        weeks: int = kwargs.get("weeks", 8)
        hr_low: int = kwargs.get("hr_low", 125)
        hr_high: int = kwargs.get("hr_high", 145)
        ref_hr = round((hr_low + hr_high) / 2)

        today = date.today()
        rows = get_window(user, today.isoformat(), weeks * 7)

        indoor: list[dict] = []
        outdoor: list[dict] = []
        for r in rows:
            if not r.get("ran_today"):
                continue
            hr = r.get("run_avg_hr")
            pace = r.get("run_avg_pace_sec_per_km")
            if hr is None or pace is None or not (hr_low <= hr <= hr_high):
                continue
            ef = r.get("run_efficiency_factor")
            if ef is None:  # row predates EF-at-ingest — compute on the fly
                ef = efficiency_factor(pace, hr)
            entry = {
                "date": r["date"],
                "km": r.get("run_distance_km"),
                "pace": _fmt_pace(pace),
                "hr": hr,
                "ef": ef,
            }
            (indoor if r.get("run_is_indoor") else outdoor).append(entry)

        return {
            "success": True,
            "user": user,
            "window_weeks": weeks,
            "z2_band": {"hr_low": hr_low, "hr_high": hr_high, "ref_hr": ref_hr},
            "note": (
                "EF = speed(m/min)/HR; higher = fitter. Indoor (treadmill, set pace) and "
                "outdoor (GPS pace) trend separately, so they are reported as two buckets. "
                "Compare EF on like-for-like runs; pace_at_ref_* is pace held at ref_hr, "
                "first vs last run."
            ),
            "indoor": _summarise(indoor, ref_hr),
            "outdoor": _summarise(outdoor, ref_hr),
        }
