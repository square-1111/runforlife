"""
Tests for the z2_pace_trend skill — the aerobic-progress (EF) trend.

Sandboxed to a tmp RUNFORLIFE_HOME; no real athlete data touched.
"""

import pytest


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    from runforlife.storage import paths

    monkeypatch.setattr(paths, "RUNFORLIFE_HOME", tmp_path / ".runforlife")
    return tmp_path


def _add_run(date, pace, hr, indoor, ef=None):
    from runforlife.storage import metrics_store
    from runforlife.rag.daily_document import DailyDocument

    metrics_store.upsert_day("tezuesh", DailyDocument(
        user="tezuesh", date=date, ran_today=True, run_distance_km=5.0,
        run_avg_pace_sec_per_km=pace, run_avg_hr=hr,
        run_is_indoor=indoor, run_efficiency_factor=ef,
    ))


def test_splits_indoor_and_outdoor_and_filters_band(sandbox):
    from runforlife.skills.analysis.z2_pace_trend import Z2PaceTrend

    _add_run("2026-06-01", 350, 130, indoor=True)     # Z2 indoor
    _add_run("2026-06-02", 420, 135, indoor=False)    # Z2 outdoor
    _add_run("2026-06-03", 300, 165, indoor=True)     # HR above band → excluded

    res = Z2PaceTrend().execute(user="tezuesh", weeks=8, hr_low=125, hr_high=145)
    assert res["success"] is True
    assert res["indoor"]["n"] == 1
    assert res["outdoor"]["n"] == 1
    assert res["z2_band"]["ref_hr"] == 135


def test_computes_ef_on_the_fly_when_missing(sandbox):
    from runforlife.skills.analysis.z2_pace_trend import Z2PaceTrend

    _add_run("2026-06-01", 345, 130, indoor=True, ef=None)  # no stored EF
    res = Z2PaceTrend().execute(user="tezuesh")
    assert res["indoor"]["runs"][0]["ef"] == 1.338  # computed from pace+HR


def test_improving_indoor_trend_has_positive_slope(sandbox):
    from runforlife.skills.analysis.z2_pace_trend import Z2PaceTrend

    # Same HR, pace getting faster over time → EF rising → positive slope
    _add_run("2026-06-01", 380, 130, indoor=True)
    _add_run("2026-06-05", 360, 130, indoor=True)
    _add_run("2026-06-09", 340, 130, indoor=True)
    res = Z2PaceTrend().execute(user="tezuesh")
    assert res["indoor"]["n"] == 3
    assert res["indoor"]["ef_slope_per_run"] > 0
    # pace held at ref HR should be faster (smaller) at the end than the start
    first = res["indoor"]["pace_at_ref_first"]
    last = res["indoor"]["pace_at_ref_last"]
    assert first is not None and last is not None


def test_empty_when_no_z2_runs(sandbox):
    from runforlife.skills.analysis.z2_pace_trend import Z2PaceTrend

    res = Z2PaceTrend().execute(user="tezuesh")
    assert res["indoor"]["n"] == 0
    assert res["outdoor"]["n"] == 0
