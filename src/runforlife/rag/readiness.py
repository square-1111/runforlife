"""
Composite readiness score — research-validated multi-signal model.

Weights derived from Nuuttila et al. 2025 RCT (triple-combination group
showed greatest FTP gains) and two independent practitioner frameworks:

    HRV             20%  — normalized against 21-day personal baseline
    Sleep           25%  — Garmin sleep score / 100
    ACWR            20%  — 1.0 = perfect; degrades outside 0.8–1.3
    Subjective      25%  — daily check-in (1–10 / 10)
    RHR             10%  — normalized against 21-day baseline

Output tiers (Saw et al. 2016 conflict-resolution rule applied):
    Green  8.0–10.0 → train as planned
    Amber  5.0–7.9  → reduce volume/intensity 20–50%
    Red    0.0–4.9  → active recovery or rest only

Conflict rule: when HRV component > 0.7 but subjective ≤ 0.4 for 2+
consecutive days → downgrade to Amber regardless of HRV signal.
"""

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date, timedelta

from runforlife import config
from runforlife.storage.metrics_store import get_recent, get_window


@dataclass
class ReadinessResult:
    score: float         # 0–10
    tier: str            # "Green" | "Amber" | "Red"
    summary_line: str    # one-line human-readable verdict
    conflict_detected: bool
    components: dict     # individual scores for transparency


def _acwr_score(acwr: float | None) -> float:
    """Map ACWR to 0–1. 1.0 = optimal, degrades outside 0.8–1.3."""
    if acwr is None:
        return 0.5  # neutral when missing
    if 0.8 <= acwr <= 1.3:
        # Linear peak at 1.0
        return 1.0 - abs(acwr - 1.0) / 0.5 * 0.2
    if acwr < 0.8:
        # Under-training
        return max(0.0, 0.6 - (0.8 - acwr) * 1.5)
    # Over-training: acwr > 1.3
    if acwr > 1.5:
        return max(0.0, 0.3 - (acwr - 1.5) * 0.5)
    return max(0.0, 0.8 - (acwr - 1.3) * 1.0)


def _normalize_against_baseline(value: float | None, baseline: float | None, higher_is_better: bool = True) -> float:
    """Normalize a metric against personal baseline. Returns 0–1."""
    if value is None or baseline is None or baseline == 0:
        return 0.5
    ratio = value / baseline
    if higher_is_better:
        return min(1.0, max(0.0, ratio))
    else:
        # For RHR: lower is better — ratio < 1 means lower than baseline (good)
        return min(1.0, max(0.0, 2.0 - ratio))


def compute_readiness(user: str, target_date: str | None = None) -> ReadinessResult:
    """
    Compute composite readiness for a given date (defaults to today).
    """
    if target_date is None:
        target_date = date.today().isoformat()

    # Get today's data
    window_21 = get_window(user, target_date, 21)
    today_row = next((r for r in window_21 if r["date"] == target_date), None)

    # 21-day baselines (exclude today for unbiased baseline)
    baseline_rows = [r for r in window_21 if r["date"] < target_date]

    def baseline(key: str) -> float | None:
        vals = [r[key] for r in baseline_rows if r.get(key) is not None]
        return sum(vals) / len(vals) if vals else None

    hrv_baseline = baseline("hrv_last_night")
    rhr_baseline = baseline("resting_hr")

    # Extract today's values
    hrv_today = today_row.get("hrv_last_night") if today_row else None
    rhr_today = today_row.get("resting_hr") if today_row else None
    sleep_score = today_row.get("sleep_score") if today_row else None
    acwr = today_row.get("acwr") if today_row else None
    subjective = today_row.get("subjective_readiness") if today_row else None

    # Component scores (all 0–1)
    hrv_component   = _normalize_against_baseline(hrv_today, hrv_baseline, higher_is_better=True)
    sleep_component = (sleep_score / 100.0) if sleep_score is not None else 0.5
    acwr_component  = _acwr_score(acwr)
    subj_component  = (subjective / 10.0) if subjective is not None else 0.5
    rhr_component   = _normalize_against_baseline(rhr_today, rhr_baseline, higher_is_better=False)

    # Weighted composite
    score_raw = (
        hrv_component   * 0.20 +
        sleep_component * 0.25 +
        acwr_component  * 0.20 +
        subj_component  * 0.25 +
        rhr_component   * 0.10
    )
    score = round(score_raw * 10, 1)

    # Conflict detection: HRV looks good but subjective has been low 2+ days
    conflict = False
    if hrv_component > 0.7 and subjective is not None and subjective <= 4:
        recent_2 = get_window(user, target_date, 2)
        low_subj_days = sum(
            1 for r in recent_2
            if r.get("subjective_readiness") is not None and r["subjective_readiness"] <= 4
        )
        if low_subj_days >= 2:
            conflict = True
            score = min(score, 7.0)  # cap at top of Amber

    # Determine tier
    if score >= 8.0:
        tier = "Green"
    elif score >= 5.0:
        tier = "Amber"
    else:
        tier = "Red"

    # Build summary line
    parts = []
    if hrv_today is not None and hrv_baseline is not None:
        delta = hrv_today - hrv_baseline
        sign = "+" if delta >= 0 else ""
        parts.append(f"HRV {hrv_today:.0f}ms ({sign}{delta:.0f} vs baseline)")
    if sleep_score is not None:
        parts.append(f"sleep {sleep_score}")
    if acwr is not None:
        parts.append(f"ACWR {acwr:.2f}")
    if subjective is not None:
        parts.append(f"subjective {subjective}/10")
    if conflict:
        parts.append("⚠ HRV-subjective conflict overriding to Amber")

    tier_symbol = {"Green": "🟢", "Amber": "🟡", "Red": "🔴"}[tier]
    summary = f"{tier_symbol} {tier.upper()} ({score}/10) — " + (", ".join(parts) if parts else "insufficient data")

    return ReadinessResult(
        score=score,
        tier=tier,
        summary_line=summary,
        conflict_detected=conflict,
        components={
            "hrv":       round(hrv_component, 2),
            "sleep":     round(sleep_component, 2),
            "acwr":      round(acwr_component, 2),
            "subjective": round(subj_component, 2),
            "rhr":       round(rhr_component, 2),
        },
    )


def main() -> int:
    """CLI entry point. Prints readiness as JSON to stdout."""
    parser = argparse.ArgumentParser(
        prog="python -m runforlife.rag.readiness",
        description="Compute composite readiness score for an athlete.",
    )
    parser.add_argument(
        "--user",
        required=True,
        choices=config.USERS,
        help="Athlete to compute readiness for.",
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Target date (YYYY-MM-DD). Defaults to today.",
    )
    args = parser.parse_args()

    try:
        result = compute_readiness(args.user, args.date)
    except Exception as exc:  # noqa: BLE001 — surface as JSON error to caller
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1

    payload = {
        "score": result.score,
        "tier": result.tier,
        "conflict_detected": result.conflict_detected,
        "components": result.components,
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
