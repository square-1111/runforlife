"""
Tests for the additive readiness signals (RANK 11):

  - sleep-architecture flag from deep_sleep_min / rem_sleep_min
  - HRV-downtrend flag from stored hrv_7d_slope vs config.HRV_SLOPE_WARNING
  - HRV-vs-Garmin-baseline-band note from hrv_baseline_low / hrv_baseline_high

These are ADDITIVE — they appear in the returned `components` dict but MUST NOT
destabilise the existing score / tier contract. The score is still driven by the
five original weighted components (hrv, sleep, acwr, subjective, rhr).

All storage is redirected to a tmp dir — never touches real ~/.runforlife.
"""

import pytest

from runforlife import config


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """Redirect athlete storage to a throwaway dir."""
    from runforlife.storage import paths

    monkeypatch.setattr(paths, "RUNFORLIFE_HOME", tmp_path / ".runforlife")
    return tmp_path


def _seed(user, date, **fields):
    """Insert a raw metrics row directly (bypassing DailyDocument) so we can set
    sleep-architecture / hrv-slope / baseline-band columns that the document
    pipeline does not own."""
    from runforlife.storage.metrics_store import _conn

    fields = {"user_id": user, "date": date, "ran_today": 0, **fields}
    cols = ", ".join(fields.keys())
    placeholders = ", ".join("?" * len(fields))
    with _conn(user) as conn:
        conn.execute(
            f"INSERT INTO daily_metrics ({cols}) VALUES ({placeholders})",
            list(fields.values()),
        )
        conn.commit()


# --- existing contract is preserved -----------------------------------------

def test_existing_components_keys_still_present(sandbox):
    from runforlife.rag.readiness import compute_readiness

    _seed("tezuesh", "2026-06-01", sleep_score=80, hrv_last_night=70.0, resting_hr=48)
    result = compute_readiness("tezuesh", "2026-06-01")

    for key in ("hrv", "sleep", "acwr", "subjective", "rhr"):
        assert key in result.components
    assert result.tier in ("Green", "Amber", "Red")
    assert 0.0 <= result.score <= 10.0


def test_score_unchanged_by_new_signals(sandbox):
    """A row with sleep-architecture / hrv-slope / baseline data must produce the
    SAME numeric score as one without it — the new components are informational."""
    from runforlife.rag.readiness import compute_readiness

    _seed("tezuesh", "2026-06-01", sleep_score=80, hrv_last_night=70.0, resting_hr=48)
    base = compute_readiness("tezuesh", "2026-06-01")

    _seed(
        "kakul", "2026-06-01", sleep_score=80, hrv_last_night=70.0, resting_hr=48,
        sleep_duration_min=420, deep_sleep_min=20, rem_sleep_min=15,
        hrv_7d_slope=-3.0, hrv_baseline_low=60, hrv_baseline_high=90,
    )
    enriched = compute_readiness("kakul", "2026-06-01")

    assert enriched.score == base.score
    assert enriched.tier == base.tier


# --- sleep architecture flag -------------------------------------------------

def test_low_rem_night_is_flagged(sandbox):
    from runforlife.rag.readiness import compute_readiness

    # 420 min night, only 10 min REM (~2.4%) and 80 min deep (~19%) → low REM.
    _seed(
        "tezuesh", "2026-06-02", sleep_score=75,
        sleep_duration_min=420, deep_sleep_min=80, rem_sleep_min=10,
    )
    result = compute_readiness("tezuesh", "2026-06-02")
    arch = result.components["sleep_architecture"]
    assert arch["low_rem"] is True
    assert arch["low_deep"] is False


def test_low_deep_night_is_flagged(sandbox):
    from runforlife.rag.readiness import compute_readiness

    # 420 min night, only 20 min deep (~4.8%), healthy REM 100 min (~24%).
    _seed(
        "tezuesh", "2026-06-03", sleep_score=75,
        sleep_duration_min=420, deep_sleep_min=20, rem_sleep_min=100,
    )
    result = compute_readiness("tezuesh", "2026-06-03")
    arch = result.components["sleep_architecture"]
    assert arch["low_deep"] is True
    assert arch["low_rem"] is False


def test_healthy_sleep_architecture_not_flagged(sandbox):
    from runforlife.rag.readiness import compute_readiness

    # 420 min, deep 80 (~19%), REM 100 (~24%) — both healthy.
    _seed(
        "tezuesh", "2026-06-04", sleep_score=85,
        sleep_duration_min=420, deep_sleep_min=80, rem_sleep_min=100,
    )
    result = compute_readiness("tezuesh", "2026-06-04")
    arch = result.components["sleep_architecture"]
    assert arch["low_deep"] is False
    assert arch["low_rem"] is False


def test_sleep_architecture_missing_data_handled(sandbox):
    from runforlife.rag.readiness import compute_readiness

    _seed("tezuesh", "2026-06-05", sleep_score=70)  # no stage breakdown
    result = compute_readiness("tezuesh", "2026-06-05")
    arch = result.components["sleep_architecture"]
    assert arch["low_deep"] is None
    assert arch["low_rem"] is None


# --- HRV downtrend flag ------------------------------------------------------

def test_negative_hrv_slope_flags_downtrend(sandbox):
    from runforlife.rag.readiness import compute_readiness

    _seed("tezuesh", "2026-06-06", sleep_score=75, hrv_7d_slope=-3.5)
    result = compute_readiness("tezuesh", "2026-06-06")
    assert result.components["hrv_downtrend"] is True


def test_flat_hrv_slope_no_downtrend(sandbox):
    from runforlife.rag.readiness import compute_readiness

    # slope above the warning threshold (config.HRV_SLOPE_WARNING == -1.0)
    _seed("tezuesh", "2026-06-07", sleep_score=75, hrv_7d_slope=-0.2)
    result = compute_readiness("tezuesh", "2026-06-07")
    assert result.components["hrv_downtrend"] is False


def test_hrv_slope_at_threshold_not_flagged(sandbox):
    from runforlife.rag.readiness import compute_readiness

    _seed("tezuesh", "2026-06-08", sleep_score=75, hrv_7d_slope=config.HRV_SLOPE_WARNING)
    result = compute_readiness("tezuesh", "2026-06-08")
    # Exactly at the warning threshold should NOT trip (strictly-below rule).
    assert result.components["hrv_downtrend"] is False


def test_hrv_slope_missing_handled(sandbox):
    from runforlife.rag.readiness import compute_readiness

    _seed("tezuesh", "2026-06-09", sleep_score=75)
    result = compute_readiness("tezuesh", "2026-06-09")
    assert result.components["hrv_downtrend"] is None


# --- HRV vs Garmin baseline band --------------------------------------------

def test_hrv_below_baseline_band(sandbox):
    from runforlife.rag.readiness import compute_readiness

    _seed(
        "tezuesh", "2026-06-10", sleep_score=75,
        hrv_last_night=50.0, hrv_baseline_low=60, hrv_baseline_high=90,
    )
    result = compute_readiness("tezuesh", "2026-06-10")
    assert result.components["hrv_baseline_position"] == "below"


def test_hrv_within_baseline_band(sandbox):
    from runforlife.rag.readiness import compute_readiness

    _seed(
        "tezuesh", "2026-06-11", sleep_score=75,
        hrv_last_night=72.0, hrv_baseline_low=60, hrv_baseline_high=90,
    )
    result = compute_readiness("tezuesh", "2026-06-11")
    assert result.components["hrv_baseline_position"] == "within"


def test_hrv_above_baseline_band(sandbox):
    from runforlife.rag.readiness import compute_readiness

    _seed(
        "tezuesh", "2026-06-12", sleep_score=75,
        hrv_last_night=95.0, hrv_baseline_low=60, hrv_baseline_high=90,
    )
    result = compute_readiness("tezuesh", "2026-06-12")
    assert result.components["hrv_baseline_position"] == "above"


def test_hrv_baseline_band_missing_handled(sandbox):
    from runforlife.rag.readiness import compute_readiness

    _seed("tezuesh", "2026-06-13", sleep_score=75, hrv_last_night=72.0)
    result = compute_readiness("tezuesh", "2026-06-13")
    assert result.components["hrv_baseline_position"] is None
