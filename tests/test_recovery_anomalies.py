"""
Tests for the read-only recovery-anomaly summarizer (RANK 19, ADDITIVE ONLY).

The coach is reactive — it only surfaces recovery anomalies when asked. This
summarizer collects any firing anomalies for the active athlete (from the
readiness signals plus the recent RHR slope and ACWR) and returns a short list
of plain-language flags, EMPTY when everything is clear. It is read-only and
must not touch the readiness score / tier contract.

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
    """Insert a raw metrics row directly so we can set sleep-architecture /
    hrv-slope / rhr-slope / acwr columns the document pipeline does not own."""
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


# --- all-clear returns an empty list ----------------------------------------

def test_healthy_athlete_has_no_anomalies(sandbox):
    from runforlife.skills.analysis.recovery_anomalies import collect_anomalies

    # Healthy: REM ~24%, deep ~19%, flat HRV slope, HRV within band, flat RHR,
    # ACWR in the safe zone.
    _seed(
        "tezuesh", "2026-06-13", sleep_score=85,
        hrv_last_night=72.0, resting_hr=48,
        sleep_duration_min=420, deep_sleep_min=80, rem_sleep_min=100,
        hrv_7d_slope=0.1, hrv_baseline_low=60, hrv_baseline_high=90,
        rhr_7d_slope=0.0, acwr=1.0,
    )
    assert collect_anomalies("tezuesh", "2026-06-13") == []


def test_no_data_day_returns_empty(sandbox):
    """A day with no row at all must fail-open to an empty list, never raise."""
    from runforlife.skills.analysis.recovery_anomalies import collect_anomalies

    assert collect_anomalies("tezuesh", "2026-06-13") == []


# --- individual anomalies fire ----------------------------------------------

def test_low_rem_is_flagged(sandbox):
    from runforlife.skills.analysis.recovery_anomalies import collect_anomalies

    # 420 min night, only 10 min REM (~2.4%) → low REM.
    _seed(
        "tezuesh", "2026-06-13", sleep_score=75,
        sleep_duration_min=420, deep_sleep_min=80, rem_sleep_min=10,
    )
    flags = collect_anomalies("tezuesh", "2026-06-13")
    assert any("REM" in f for f in flags)


def test_low_deep_is_flagged(sandbox):
    from runforlife.skills.analysis.recovery_anomalies import collect_anomalies

    _seed(
        "tezuesh", "2026-06-13", sleep_score=75,
        sleep_duration_min=420, deep_sleep_min=20, rem_sleep_min=100,
    )
    flags = collect_anomalies("tezuesh", "2026-06-13")
    assert any("deep" in f.lower() for f in flags)


def test_negative_hrv_slope_flags_downtrend(sandbox):
    from runforlife.skills.analysis.recovery_anomalies import collect_anomalies

    _seed("tezuesh", "2026-06-13", sleep_score=75, hrv_7d_slope=-3.5)
    flags = collect_anomalies("tezuesh", "2026-06-13")
    assert any("HRV" in f and "down" in f.lower() for f in flags)


def test_flat_hrv_slope_no_downtrend(sandbox):
    from runforlife.skills.analysis.recovery_anomalies import collect_anomalies

    # Above the warning threshold (config.HRV_SLOPE_WARNING == -1.0).
    _seed("tezuesh", "2026-06-13", sleep_score=75, hrv_7d_slope=-0.2)
    flags = collect_anomalies("tezuesh", "2026-06-13")
    assert not any("down" in f.lower() for f in flags)


def test_hrv_below_baseline_band_is_flagged(sandbox):
    from runforlife.skills.analysis.recovery_anomalies import collect_anomalies

    _seed(
        "tezuesh", "2026-06-13", sleep_score=75,
        hrv_last_night=50.0, hrv_baseline_low=60, hrv_baseline_high=90,
    )
    flags = collect_anomalies("tezuesh", "2026-06-13")
    assert any("baseline" in f.lower() for f in flags)


def test_climbing_rhr_is_flagged(sandbox):
    from runforlife.skills.analysis.recovery_anomalies import collect_anomalies

    _seed("tezuesh", "2026-06-13", sleep_score=75, rhr_7d_slope=1.5)
    flags = collect_anomalies("tezuesh", "2026-06-13")
    assert any("RHR" in f for f in flags)


def test_flat_rhr_not_flagged(sandbox):
    from runforlife.skills.analysis.recovery_anomalies import collect_anomalies

    _seed("tezuesh", "2026-06-13", sleep_score=75, rhr_7d_slope=0.2)
    flags = collect_anomalies("tezuesh", "2026-06-13")
    assert not any("RHR" in f for f in flags)


def test_elevated_acwr_is_flagged(sandbox):
    from runforlife.skills.analysis.recovery_anomalies import collect_anomalies

    # Above the safe max but below the high-risk line.
    acwr = (config.ACWR_SAFE_MAX + config.ACWR_HIGH_RISK) / 2
    _seed("tezuesh", "2026-06-13", sleep_score=75, acwr=acwr)
    flags = collect_anomalies("tezuesh", "2026-06-13")
    assert any("ACWR" in f or "load" in f.lower() for f in flags)


def test_high_risk_acwr_is_flagged(sandbox):
    from runforlife.skills.analysis.recovery_anomalies import collect_anomalies

    _seed("tezuesh", "2026-06-13", sleep_score=75, acwr=config.ACWR_HIGH_RISK + 0.3)
    flags = collect_anomalies("tezuesh", "2026-06-13")
    assert any("ACWR" in f or "load" in f.lower() for f in flags)


def test_safe_acwr_not_flagged(sandbox):
    from runforlife.skills.analysis.recovery_anomalies import collect_anomalies

    _seed("tezuesh", "2026-06-13", sleep_score=75, acwr=1.1)
    flags = collect_anomalies("tezuesh", "2026-06-13")
    assert not any("ACWR" in f or "load" in f.lower() for f in flags)


# --- combined / shape --------------------------------------------------------

def test_multiple_anomalies_all_surface(sandbox):
    from runforlife.skills.analysis.recovery_anomalies import collect_anomalies

    # The validated-live combo: low REM + HRV downtrend together.
    _seed(
        "tezuesh", "2026-06-13", sleep_score=70,
        sleep_duration_min=420, deep_sleep_min=80, rem_sleep_min=10,
        hrv_7d_slope=-3.0,
    )
    flags = collect_anomalies("tezuesh", "2026-06-13")
    assert len(flags) >= 2
    assert all(isinstance(f, str) and f.strip() for f in flags)


def test_returns_list_of_plain_strings(sandbox):
    from runforlife.skills.analysis.recovery_anomalies import collect_anomalies

    _seed("tezuesh", "2026-06-13", sleep_score=75, rhr_7d_slope=2.0)
    flags = collect_anomalies("tezuesh", "2026-06-13")
    assert isinstance(flags, list)
    assert all(isinstance(f, str) for f in flags)
