"""
Tests for correlate_metrics run-metric support.

The skill's description promises HRV-vs-pace correlation, but the
AVAILABLE_METRICS list previously omitted run pace/HR/vo2max columns, so
those questions could never be asked. These tests insert run rows via
metrics_store.upsert_day and confirm the new run metrics are both exposed
and correlatable end-to-end.

All storage is redirected to a tmp dir — never touches real ~/.runforlife.
"""

import pytest


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """Redirect athlete storage to a throwaway dir.

    metrics_store paths resolve from paths.RUNFORLIFE_HOME (athlete_dir), so
    patching it isolates all storage to a tmp dir — never touches real
    ~/.runforlife.
    """
    from runforlife.storage import paths

    monkeypatch.setattr(paths, "RUNFORLIFE_HOME", tmp_path / ".runforlife")
    return tmp_path


# --- new run metrics are exposed ---------------------------------------------

def test_new_run_metrics_are_available():
    from runforlife.skills.analysis.correlate_metrics import AVAILABLE_METRICS

    for metric in (
        "run_avg_pace_sec_per_km",
        "run_avg_hr",
        "vo2_max",
        "training_effect_aerobic",
        "run_efficiency_factor",
    ):
        assert metric in AVAILABLE_METRICS


def test_pace_metric_in_skill_input_enum():
    """The input schema enums are built from AVAILABLE_METRICS, so the new
    columns must be selectable as metric_x / metric_y."""
    from runforlife.skills.analysis.correlate_metrics import CorrelateMetrics

    schema = CorrelateMetrics.input_schema
    assert "run_avg_pace_sec_per_km" in schema["properties"]["metric_x"]["enum"]
    assert "run_avg_pace_sec_per_km" in schema["properties"]["metric_y"]["enum"]


# --- end-to-end correlation over real DB rows --------------------------------

def _seed_run_days(user, n=8):
    """Insert n consecutive run days with varying HRV + pace + HR."""
    from runforlife.storage import metrics_store
    from runforlife.rag.daily_document import DailyDocument

    for i in range(n):
        date = f"2026-06-{i + 1:02d}"
        doc = DailyDocument(
            user=user,
            date=date,
            hrv_last_night=60.0 + i,            # rising HRV
            ran_today=True,
            run_distance_km=8.0,
            run_avg_pace_sec_per_km=360.0 - i * 5,  # faster pace as HRV rises
            run_avg_hr=145 + i,
            vo2_max=52.0 + i * 0.1,
            training_effect_aerobic=2.5 + i * 0.1,
            run_efficiency_factor=1.30 + i * 0.01,
        )
        metrics_store.upsert_day(user, doc)


def test_correlate_hrv_vs_pace_runs_without_error(sandbox):
    from runforlife.skills.analysis.correlate_metrics import CorrelateMetrics

    _seed_run_days("tezuesh", n=8)

    result = CorrelateMetrics().execute(
        user="tezuesh",
        metric_x="hrv_last_night",
        metric_y="run_avg_pace_sec_per_km",
        window_days=90,
        end_date="2026-06-09",
    )

    assert result["success"] is True
    assert result["metric_y"] == "run_avg_pace_sec_per_km"
    assert result["n_data_points"] == 8
    # HRV rises while pace falls → strong negative correlation expected.
    assert result["pearson_r"] is not None
    assert result["pearson_r"] < 0


def test_correlate_new_metrics_round_trip_from_db(sandbox):
    """Each newly added run metric must be readable as a y-series from the DB."""
    from runforlife.skills.analysis.correlate_metrics import CorrelateMetrics

    _seed_run_days("tezuesh", n=8)

    for metric in (
        "run_avg_hr",
        "vo2_max",
        "training_effect_aerobic",
        "run_efficiency_factor",
    ):
        result = CorrelateMetrics().execute(
            user="tezuesh",
            metric_x="hrv_last_night",
            metric_y=metric,
            end_date="2026-06-09",
        )
        assert result["success"] is True, metric
        assert result["n_data_points"] == 8, metric
        assert result["pearson_r"] is not None, metric
