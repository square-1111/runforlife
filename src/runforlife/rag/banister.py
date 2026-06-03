"""
Simplified Banister Fitness-Fatigue Model.

Estimates:
  CTL (Chronic Training Load / Fitness)  — 42-day EMA of daily training load
  ATL (Acute Training Load / Fatigue)    — 7-day EMA of daily training load
  TSB (Training Stress Balance)          — CTL - ATL

TSB interpretation:
  > +10  : fresh/rested — taper zone or undertraining
   0–+10 : optimal racing form
 -10–0  : productive fatigue — normal build phase
  < -10  : accumulated fatigue — reduce load
  < -20  : overreaching risk — mandatory recovery

Training load proxy: distance_km × intensity_factor × 10
  intensity_factor = max(0.5, 1 - (pace_sec_per_km - 240) / 360)
  Easy runs (~360 s/km) → factor ≈ 0.67; fast runs (~270 s/km) → factor ≈ 0.92
"""

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import date

from runforlife import config
from runforlife.storage.metrics_store import get_window


@dataclass
class BanisterState:
    fitness: float           # CTL
    fatigue: float           # ATL
    tsb: float               # Training Stress Balance
    trend: str               # "building" | "peaking" | "overreaching" | "recovering" | "detraining"
    overreaching_risk: str   # "low" | "moderate" | "high"
    summary: str


def compute_banister(user: str) -> BanisterState | None:
    """
    Compute CTL/ATL/TSB from stored metrics. Returns None if < 14 days of data.
    """
    today = date.today().isoformat()
    rows = get_window(user, today, 90)
    if len(rows) < 14:
        return None

    alpha_ctl = 2.0 / (42 + 1)   # 42-day decay constant
    alpha_atl = 2.0 / (7 + 1)    # 7-day decay constant
    ctl = 0.0
    atl = 0.0

    for r in rows:
        load = _daily_load(r)
        ctl = alpha_ctl * load + (1 - alpha_ctl) * ctl
        atl = alpha_atl * load + (1 - alpha_atl) * atl

    tsb = ctl - atl

    # Trend based on ATL:CTL ratio and recent TSB direction
    recent = rows[-7:]
    recent_loads = [_daily_load(r) for r in recent]
    recent_avg = sum(recent_loads) / len(recent_loads)

    if atl > ctl * 1.4 or tsb < -15:
        trend = "overreaching"
    elif atl > ctl * 1.1 and recent_avg > 0:
        trend = "building"
    elif tsb > 10 and recent_avg < ctl * 0.6:
        trend = "recovering"
    elif recent_avg < ctl * 0.3:
        trend = "detraining"
    else:
        trend = "peaking"

    if atl > ctl * 1.4 or tsb < -20:
        risk = "high"
    elif atl > ctl * 1.2 or tsb < -10:
        risk = "moderate"
    else:
        risk = "low"

    ctl_r = round(ctl, 1)
    atl_r = round(atl, 1)
    tsb_r = round(tsb, 1)
    sign = "+" if tsb_r >= 0 else ""

    summary = (
        f"Fitness (CTL): {ctl_r} | Fatigue (ATL): {atl_r} | "
        f"Balance (TSB): {sign}{tsb_r} | Trend: {trend.title()} | "
        f"Overreaching risk: {risk.title()}"
    )

    return BanisterState(
        fitness=ctl_r,
        fatigue=atl_r,
        tsb=tsb_r,
        trend=trend,
        overreaching_risk=risk,
        summary=summary,
    )


def _daily_load(row: dict) -> float:
    """Compute training load for one day. Returns 0 if no run."""
    if not row.get("ran_today"):
        return 0.0
    dist = row.get("run_distance_km")
    if not dist:
        return 0.0
    pace = row.get("run_avg_pace_sec_per_km") or 360
    intensity = max(0.5, 1.0 - (pace - 240) / 360)
    return dist * intensity * 10


def main() -> int:
    """CLI entry point. Prints Banister state as JSON to stdout."""
    parser = argparse.ArgumentParser(
        prog="python -m runforlife.rag.banister",
        description="Compute CTL/ATL/TSB Banister fitness-fatigue state for an athlete.",
    )
    parser.add_argument(
        "--user",
        required=True,
        choices=config.USERS,
        help="Athlete to compute Banister state for.",
    )
    args = parser.parse_args()

    try:
        state = compute_banister(args.user)
    except Exception as exc:  # noqa: BLE001 — surface as JSON error to caller
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1

    if state is None:
        print(json.dumps({"error": "insufficient data: fewer than 14 days of metrics"}), file=sys.stderr)
        return 1

    print(json.dumps(asdict(state), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
