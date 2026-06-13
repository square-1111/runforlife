"""
Tests for the canonical daily training-load definition (features.daily_load).

Pins:
  - known pace -> known load (pace-weighted distance formula)
  - paceless runs fall back to a *flagged* estimate (not a silent default)
  - the Banister model and the canonical function agree numerically
    (load is defined exactly once)

Pure functions, no I/O — no storage sandbox needed. The Banister-consistency
test calls only banister._daily_load (a pure row->float adapter), never touches
the DB, and never runs Garmin sync.
"""

from runforlife.rag.banister import _daily_load
from runforlife.rag.features import (
    PACELESS_FALLBACK_SEC_PER_KM,
    daily_load,
)


# --- known pace -> known load ------------------------------------------------

def test_daily_load_threshold_pace_full_intensity():
    # pace 240 s/km -> intensity max(0.5, 1 - 0) = 1.0 -> 10 km * 1.0 * 10 = 100
    result = daily_load(10.0, 240)
    assert result.value == 100.0
    assert result.estimated is False


def test_daily_load_easy_pace_known_value():
    # pace 360 s/km -> intensity 1 - (360-240)/360 = 1 - 0.333.. = 0.666..
    # 10 km * 0.6667 * 10 = 66.67
    result = daily_load(10.0, 360)
    assert round(result.value, 2) == 66.67
    assert result.estimated is False


def test_daily_load_intensity_floor_at_half():
    # Very slow pace clamps intensity to the 0.5 floor: 10 * 0.5 * 10 = 50
    assert daily_load(10.0, 600).value == 50.0


def test_daily_load_no_distance_is_zero_not_estimated():
    assert daily_load(0.0, 300) == (0.0, False)
    assert daily_load(None, 300) == (0.0, False)


# --- paceless fallback is a FLAGGED estimate ---------------------------------

def test_daily_load_paceless_is_flagged_estimate():
    result = daily_load(10.0, None)
    assert result.estimated is True
    # Falls back to the historical 360 s/km assumption -> same as easy pace.
    assert result.value == daily_load(10.0, PACELESS_FALLBACK_SEC_PER_KM).value


def test_daily_load_paceless_matches_legacy_360_default():
    # Numerically neutral vs the old `pace = pace or 360` behaviour.
    assert round(daily_load(8.0, None).value, 4) == round(daily_load(8.0, 360).value, 4)


def test_daily_load_avg_hr_is_ignored_today():
    # avg_hr accepted for signature stability but must not change the number.
    assert daily_load(10.0, 300, avg_hr=150).value == daily_load(10.0, 300).value


# --- banister and the canonical function are the SAME function ---------------

def test_banister_load_uses_canonical_daily_load():
    row = {"ran_today": True, "run_distance_km": 12.0, "run_avg_pace_sec_per_km": 300}
    assert _daily_load(row) == daily_load(12.0, 300).value


def test_banister_paceless_matches_canonical_estimate():
    row = {"ran_today": True, "run_distance_km": 9.0, "run_avg_pace_sec_per_km": None}
    assert _daily_load(row) == daily_load(9.0, None).value


def test_banister_no_run_is_zero():
    assert _daily_load({"ran_today": False, "run_distance_km": 10.0}) == 0.0
    assert _daily_load({"ran_today": True, "run_distance_km": None}) == 0.0
