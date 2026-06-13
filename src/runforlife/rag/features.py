"""
Feature engineering for injury risk signals.

Computes window-based features from stored Chroma metadata.
Called during ingestion after a day's raw data is stored.

Key features:
  ACWR       — Acute:Chronic Workload Ratio (7d acute / 28d chronic)
               Safe zone: 0.8–1.3. Above 1.5 = 2-4x injury risk.
  HRV slope  — Linear slope of HRV over past 7 days (ms/day)
               Negative slope = recovery stress accumulating
  Sleep Δ    — Today's sleep efficiency vs 28-day rolling baseline (pp)
               Persistent negative delta flags sleep quality degradation
  RHR slope  — Linear slope of resting HR over 7 days (bpm/day)
               Rising RHR with declining HRV = strong overtraining signal
"""

from typing import NamedTuple

import numpy as np

# --- canonical daily training load -------------------------------------------
#
# Single source of truth for per-day training load. Both the Banister
# fitness-fatigue model (banister.py) and any pace-weighted load consumer read
# this so "load" is defined exactly once.
#
#   load = distance_km × intensity_factor × 10
#   intensity_factor = max(0.5, 1 - (pace_sec_per_km - 240) / 360)
#
# Easy runs (~360 s/km) → factor ≈ 0.67; fast runs (~270 s/km) → factor ≈ 0.92.
# This is the formula that has always lived in banister._daily_load; it is
# reused verbatim here so existing CTL/ATL/TSB numbers do not shift.

# Pace (s/km) assumed when a run has distance but no recorded pace. Matches the
# historical Banister fallback so de-duplication is numerically neutral.
PACELESS_FALLBACK_SEC_PER_KM = 360.0


class DailyLoad(NamedTuple):
    """Result of :func:`daily_load`.

    value:     the training-load number (0.0 when there is no run).
    estimated: True when pace was missing and a fallback pace was assumed, so
               callers can flag the load as an estimate instead of silently
               trusting a defaulted value.
    """

    value: float
    estimated: bool


def daily_load(
    distance_km: float | None,
    pace_sec_per_km: float | None,
    avg_hr: float | None = None,
) -> DailyLoad:
    """Canonical per-day training load (pace-weighted distance).

    Returns a :class:`DailyLoad` so the paceless case is a *flagged* estimate
    rather than a silent default.

    avg_hr is accepted for signature stability (a future HR-weighted variant /
    Garmin Training Load could use it) but is intentionally unused today — we do
    not invent an HR-based proxy from unstored data.

    Examples:
      daily_load(10, 240)  → load 100.0, estimated False  (intensity 1.0)
      daily_load(10, 360)  → load  66.7, estimated False  (intensity ~0.667)
      daily_load(10, None) → load  66.7, estimated True    (360 s/km assumed)
    """
    if not distance_km:
        return DailyLoad(0.0, estimated=False)

    estimated = not pace_sec_per_km
    pace = pace_sec_per_km if pace_sec_per_km else PACELESS_FALLBACK_SEC_PER_KM
    intensity = max(0.5, 1.0 - (pace - 240) / 360)
    return DailyLoad(distance_km * intensity * 10, estimated=estimated)


def linear_slope(values: list[float]) -> float | None:
    """
    Fit a line y = mx + b to values and return slope m.

    Returns None if fewer than 3 data points (can't fit meaningfully).
    """
    clean = [v for v in values if v is not None]
    if len(clean) < 3:
        return None
    x = np.arange(len(clean), dtype=float)
    y = np.array(clean, dtype=float)
    # Least squares: slope = (n*Σxy - Σx*Σy) / (n*Σx² - (Σx)²)
    n = len(x)
    slope = (n * np.dot(x, y) - x.sum() * y.sum()) / (n * (x**2).sum() - x.sum() ** 2)
    return float(slope)


def compute_acwr(acute_loads: list[float], chronic_loads: list[float]) -> float | None:
    """
    Compute ACWR from rolling load windows.

    acute_loads:   7 days of training load values (e.g. Training Load from Garmin)
    chronic_loads: 28 days of training load values

    Returns ratio of 7-day average to 28-day average, or None if insufficient data.
    """
    acute = [v for v in acute_loads if v is not None]
    chronic = [v for v in chronic_loads if v is not None]

    if len(acute) < 3 or len(chronic) < 7:
        return None

    acute_avg = np.mean(acute)
    chronic_avg = np.mean(chronic)

    if chronic_avg == 0:
        return None

    return float(acute_avg / chronic_avg)


def efficiency_factor(pace_sec_per_km: float | None, avg_hr: float | None) -> float | None:
    """Running Efficiency Factor (Friel): speed in metres/minute ÷ average HR.

    A pace-per-heartbeat measure of aerobic efficiency. Higher = fitter (more
    distance per beat). Because it normalises pace by HR, it exposes fitness
    gains that raw pace hides when the athlete holds effort down (e.g. heat,
    base-building). Returns None if pace or HR is missing/invalid.

    Example: 5:45/km (345 s) at HR 130 → 60000/345 / 130 ≈ 1.338.
    """
    if not pace_sec_per_km or not avg_hr or pace_sec_per_km <= 0 or avg_hr <= 0:
        return None
    meters_per_min = 60000.0 / pace_sec_per_km
    return round(meters_per_min / avg_hr, 3)


def compute_sleep_efficiency_delta(today_efficiency: float | None, baseline_window: list[float]) -> float | None:
    """
    Delta between today's sleep efficiency and the 28-day rolling baseline.

    Returns None if today's value is missing or baseline is too short.
    """
    if today_efficiency is None:
        return None

    clean = [v for v in baseline_window if v is not None]
    if len(clean) < 7:
        return None

    baseline_avg = float(np.mean(clean))
    return today_efficiency - baseline_avg
