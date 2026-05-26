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

import numpy as np


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
