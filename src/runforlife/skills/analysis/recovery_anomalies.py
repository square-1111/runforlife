"""
Read-only recovery-anomaly summarizer (RANK 19, ADDITIVE ONLY).

The coach is reactive: it only surfaces recovery problems when an athlete asks.
This module turns the engine PROactive. For the active athlete it collects any
firing recovery anomalies and returns a short list of plain-language flags,
EMPTY when everything is clear, so the SessionStart banner can LEAD with
"RHR climbing / HRV down / low REM" instead of waiting to be asked.

Sources (all read-only, no scoring side effects):
  - readiness `components` informational signals: hrv_downtrend,
    sleep_architecture.low_rem / low_deep, hrv_baseline_position == "below"
  - the recent RHR 7-day slope (rhr_7d_slope) — climbing RHR = recovery debt
  - ACWR vs the configured safe-max / high-risk thresholds — workload spike

It NEVER recomputes or mutates the readiness score / tier contract; it only
reads the already-computed informational components plus two stored columns.
Designed to fail open: any error → no flags, never raises.
"""

from runforlife import config
from runforlife.storage.metrics_store import get_window


def _readiness_flags(user: str, target_date: str | None) -> list[str]:
    """Plain-language flags derived from the readiness informational signals."""
    from runforlife.rag.readiness import compute_readiness

    result = compute_readiness(user, target_date)
    components = result.components
    flags: list[str] = []

    if components.get("hrv_downtrend") is True:
        flags.append("HRV trending down (7-day slope)")

    if components.get("hrv_baseline_position") == "below":
        flags.append("HRV below Garmin baseline band")

    arch = components.get("sleep_architecture") or {}
    if arch.get("low_rem") is True:
        flags.append("Low REM sleep")
    if arch.get("low_deep") is True:
        flags.append("Low deep sleep")

    return flags


def _rhr_flag(today_row: dict | None) -> list[str]:
    """Flag a climbing resting-HR trend (positive 7-day slope).

    Mirrors the strictly-below rule used for the HRV downtrend: only a slope
    clearly above flat counts, so day-to-day noise does not constantly fire.
    """
    if not today_row:
        return []
    slope = today_row.get("rhr_7d_slope")
    if slope is not None and slope > -config.HRV_SLOPE_WARNING:
        # -HRV_SLOPE_WARNING == 1.0 ms/day: a meaningful upward RHR drift.
        return [f"RHR climbing ({slope:+.1f}/day over 7 days)"]
    return []


def _acwr_flag(today_row: dict | None) -> list[str]:
    """Flag an elevated / high-risk acute:chronic workload ratio."""
    if not today_row:
        return []
    acwr = today_row.get("acwr")
    if acwr is None:
        return []
    if acwr > config.ACWR_HIGH_RISK:
        return [f"ACWR {acwr:.2f} in high injury-risk zone (>{config.ACWR_HIGH_RISK})"]
    if acwr > config.ACWR_SAFE_MAX:
        return [f"ACWR {acwr:.2f} above safe zone (>{config.ACWR_SAFE_MAX})"]
    return []


def collect_anomalies(user: str, target_date: str | None = None) -> list[str]:
    """Return the firing recovery anomalies for the athlete as plain strings.

    Empty list when all signals are clear OR when data is insufficient. Never
    raises — any failure degrades to "no anomalies" so callers (e.g. the
    SessionStart banner) can stay fail-open and cheap.
    """
    try:
        flags = _readiness_flags(user, target_date)

        # The recent RHR slope + ACWR live on the target day's row. Match the
        # date exactly (not "most recent <= date") so these stay consistent with
        # the readiness signals, which key off the target_date row specifically.
        if target_date is None:
            from datetime import date as _date

            target_date = _date.today().isoformat()
        window = get_window(user, target_date, 1)
        today_row = window[-1] if window and window[-1].get("date") == target_date else None

        flags.extend(_rhr_flag(today_row))
        flags.extend(_acwr_flag(today_row))
        return flags
    except Exception:  # noqa: BLE001 — fail open, never break the caller
        return []
