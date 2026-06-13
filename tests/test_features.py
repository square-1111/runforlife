"""
Unit tests for the deterministic numeric engine (features.py).

These functions feed ACWR / HRV-slope / sleep-delta and the new Efficiency
Factor — the design says the LLM must never compute these by hand, so they must
be correct. Pure functions, no I/O.
"""

from runforlife.rag.features import (
    compute_acwr,
    compute_sleep_efficiency_delta,
    efficiency_factor,
    linear_slope,
)


# --- linear_slope ------------------------------------------------------------

def test_linear_slope_needs_three_points():
    assert linear_slope([1.0, 2.0]) is None
    assert linear_slope([]) is None


def test_linear_slope_perfect_increase():
    assert linear_slope([1.0, 2.0, 3.0, 4.0]) == 1.0


def test_linear_slope_perfect_decrease():
    assert linear_slope([4.0, 3.0, 2.0, 1.0]) == -1.0


def test_linear_slope_flat_is_zero():
    assert linear_slope([5.0, 5.0, 5.0]) == 0.0


def test_linear_slope_ignores_none():
    # Nones dropped; remaining [1,2,3] has slope 1.0
    assert linear_slope([1.0, None, 2.0, None, 3.0]) == 1.0


# --- compute_acwr ------------------------------------------------------------

def test_acwr_insufficient_data_is_none():
    assert compute_acwr([1.0, 2.0], [1.0] * 7) is None        # acute < 3
    assert compute_acwr([1.0] * 3, [1.0] * 6) is None         # chronic < 7


def test_acwr_zero_chronic_is_none():
    assert compute_acwr([5.0, 5.0, 5.0], [0.0] * 7) is None


def test_acwr_ratio():
    # acute avg 10, chronic avg 5 → 2.0
    assert compute_acwr([10.0] * 3, [5.0] * 7) == 2.0


# --- compute_sleep_efficiency_delta ------------------------------------------

def test_sleep_delta_none_today_is_none():
    assert compute_sleep_efficiency_delta(None, [80.0] * 10) is None


def test_sleep_delta_short_baseline_is_none():
    assert compute_sleep_efficiency_delta(80.0, [80.0] * 6) is None


def test_sleep_delta_value():
    # today 70, baseline avg 80 → -10
    assert compute_sleep_efficiency_delta(70.0, [80.0] * 7) == -10.0


# --- efficiency_factor -------------------------------------------------------

def test_ef_none_or_invalid_inputs():
    assert efficiency_factor(None, 130) is None
    assert efficiency_factor(345, None) is None
    assert efficiency_factor(0, 130) is None
    assert efficiency_factor(345, 0) is None


def test_ef_known_value():
    # 5:45/km = 345 s; 60000/345 = 173.913 m/min; /130 = 1.338
    assert efficiency_factor(345, 130) == 1.338


def test_ef_faster_pace_higher_ef():
    fast = efficiency_factor(300, 130)
    slow = efficiency_factor(420, 130)
    assert fast > slow


def test_ef_lower_hr_higher_ef():
    # Same pace, lower HR → more efficient → higher EF
    assert efficiency_factor(345, 125) > efficiency_factor(345, 140)
