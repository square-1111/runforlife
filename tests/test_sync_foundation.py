"""
Foundation-block tests: data-integrity fixes in the sync/storage engine.

Covers:
  - has_complete_day() — the gap-row fix (skeleton rows are NOT complete)
  - upsert_day() preserves manually-entered subjective fields on re-ingest
    (the INSERT OR REPLACE data-loss bug)
  - _build_document() populates run_is_indoor + run_temp_c
  - RUNFORLIFE_HOME env override

All storage is redirected to a tmp dir — never touches real ~/.runforlife.
"""

import importlib

import pytest


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """Redirect athlete storage to a throwaway dir."""
    from runforlife.storage import paths

    monkeypatch.setattr(paths, "RUNFORLIFE_HOME", tmp_path / ".runforlife")
    return tmp_path


# --- gap-row fix: has_complete_day -------------------------------------------

def test_no_row_is_not_complete(sandbox):
    from runforlife.storage import metrics_store

    assert metrics_store.has_complete_day("tezuesh", "2026-06-01") is False


def test_skeleton_row_from_subjective_checkin_is_not_complete(sandbox):
    """A subjective check-in before sync leaves an all-NULL-Garmin skeleton row.
    The old has_day() returned True and sync skipped it forever — this is the bug."""
    from runforlife.storage import metrics_store

    metrics_store.upsert_subjective("tezuesh", "2026-06-01", readiness=8, context="felt ok")
    assert metrics_store.has_day("tezuesh", "2026-06-01") is True       # row exists...
    assert metrics_store.has_complete_day("tezuesh", "2026-06-01") is False  # ...but incomplete


def test_row_with_garmin_wellness_is_complete(sandbox):
    from runforlife.storage import metrics_store
    from runforlife.rag.daily_document import DailyDocument

    doc = DailyDocument(user="tezuesh", date="2026-06-01", resting_hr=48, sleep_duration_min=420)
    metrics_store.upsert_day("tezuesh", doc)
    assert metrics_store.has_complete_day("tezuesh", "2026-06-01") is True


def test_run_only_day_is_complete(sandbox):
    from runforlife.storage import metrics_store
    from runforlife.rag.daily_document import DailyDocument

    doc = DailyDocument(user="tezuesh", date="2026-06-02", ran_today=True, run_distance_km=5.0)
    metrics_store.upsert_day("tezuesh", doc)
    assert metrics_store.has_complete_day("tezuesh", "2026-06-02") is True


# --- data-loss fix: upsert preserves manual fields ---------------------------

def test_reingest_preserves_subjective_fields(sandbox):
    """Re-ingesting a day must NOT wipe a logged subjective check-in / life_context_note.
    The old INSERT OR REPLACE deleted the row and erased these on every --resync."""
    from runforlife.storage import metrics_store
    from runforlife.rag.daily_document import DailyDocument

    # 1. Athlete logs a subjective note (skeleton row, no Garmin data yet)
    metrics_store.upsert_subjective(
        "tezuesh", "2026-06-03", readiness=7, context="travel day, slept poorly", rpe=4
    )
    # 2. Nightly sync ingests Garmin data for the same day
    doc = DailyDocument(user="tezuesh", date="2026-06-03", resting_hr=50, hrv_last_night=72.0,
                        ran_today=True, run_distance_km=8.0)
    metrics_store.upsert_day("tezuesh", doc)

    row = metrics_store.get_day("tezuesh", "2026-06-03")
    # Garmin data landed...
    assert row["resting_hr"] == 50
    assert row["run_distance_km"] == 8.0
    # ...AND the manual fields survived (the bug being fixed)
    assert row["subjective_readiness"] == 7
    assert row["life_context_note"] == "travel day, slept poorly"
    assert row["session_rpe"] == 4


def test_reingest_overwrites_garmin_fields(sandbox):
    """A genuine re-sync should still refresh the Garmin-owned columns."""
    from runforlife.storage import metrics_store
    from runforlife.rag.daily_document import DailyDocument

    metrics_store.upsert_day("tezuesh", DailyDocument(user="tezuesh", date="2026-06-04", resting_hr=55))
    metrics_store.upsert_day("tezuesh", DailyDocument(user="tezuesh", date="2026-06-04", resting_hr=48))
    assert metrics_store.get_day("tezuesh", "2026-06-04")["resting_hr"] == 48


# --- run environment fields: indoor + temperature ----------------------------

def _raw_with_run(type_key, dist_m=5000, speed=2.8, hr=130, tmin=None, tmax=None):
    activity = {
        "activityType": {"typeKey": type_key},
        "distance": dist_m,
        "averageSpeed": speed,
        "averageHR": hr,
        "aerobicTrainingEffect": 2.5,
    }
    if tmin is not None:
        activity["minTemperature"] = tmin
    if tmax is not None:
        activity["maxTemperature"] = tmax
    return {"sleep": None, "hrv": None, "summary": None, "vo2max": None, "activities": [activity]}


def test_outdoor_run_flags_not_indoor_and_captures_temp(sandbox):
    from runforlife.sync.ingest import _build_document

    doc = _build_document("tezuesh", "2026-06-06", _raw_with_run("running", tmin=34, tmax=37))
    assert doc.run_is_indoor is False
    assert doc.run_temp_c == 35.5


def test_treadmill_run_flags_indoor(sandbox):
    from runforlife.sync.ingest import _build_document

    doc = _build_document("tezuesh", "2026-06-02", _raw_with_run("treadmill_running", tmin=30, tmax=32))
    assert doc.run_is_indoor is True
    assert doc.run_temp_c == 31.0


def test_run_temp_none_when_absent(sandbox):
    from runforlife.sync.ingest import _build_document

    doc = _build_document("tezuesh", "2026-06-07", _raw_with_run("running"))
    assert doc.run_temp_c is None


def test_env_fields_round_trip_through_db(sandbox):
    from runforlife.storage import metrics_store
    from runforlife.sync.ingest import _build_document

    doc = _build_document("tezuesh", "2026-06-08", _raw_with_run("treadmill_running", tmin=30, tmax=30))
    metrics_store.upsert_day("tezuesh", doc)
    row = metrics_store.get_day("tezuesh", "2026-06-08")
    assert row["run_is_indoor"] == 1
    assert row["run_temp_c"] == 30.0


def test_efficiency_factor_computed_at_ingest(sandbox):
    from runforlife.sync.ingest import _build_document

    # 5000 m at 2.899 m/s → 345 s/km; HR 130 → EF 1.338
    doc = _build_document("tezuesh", "2026-06-09", _raw_with_run("running", speed=2.899, hr=130))
    assert doc.run_efficiency_factor == 1.338


# --- RUNFORLIFE_HOME env override --------------------------------------------

def test_runforlife_home_env_override(monkeypatch, tmp_path):
    target = tmp_path / "sandbox_home"
    monkeypatch.setenv("RUNFORLIFE_HOME", str(target))
    import runforlife.config as config
    importlib.reload(config)
    try:
        assert config.RUNFORLIFE_HOME == target
    finally:
        monkeypatch.delenv("RUNFORLIFE_HOME", raising=False)
        importlib.reload(config)
