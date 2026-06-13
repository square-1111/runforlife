"""
Tests for non-running activity capture (RANK 12, ADDITIVE ONLY).

The ingest pipeline historically kept only "running" activities and DROPPED
everything else (strength_training, SkiErg, sled, HIIT, cycling), so Hyrox /
strength load was invisible. These tests pin the new behavior:

  - a strength_training activity is persisted to the new activity_sessions
    table and is readable
  - running activities still populate the existing run_* fields UNCHANGED
  - a mixed day stores BOTH (run in daily_metrics, strength in activity_sessions)
  - the optional hyrox-stations read helper is safe on missing data

All storage is redirected to a tmp dir — never touches real ~/.runforlife.
"""

import pytest


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """Redirect athlete storage to a throwaway dir."""
    from runforlife.storage import paths

    monkeypatch.setattr(paths, "RUNFORLIFE_HOME", tmp_path / ".runforlife")
    return tmp_path


def _activity(type_key, dist_m=None, dur_sec=1800, hr=140, max_hr=170,
              load=None, start="2026-06-10T07:30:00.0"):
    a = {
        "activityType": {"typeKey": type_key},
        "duration": dur_sec,
        "averageHR": hr,
        "maxHR": max_hr,
        "startTimeLocal": start,
    }
    if dist_m is not None:
        a["distance"] = dist_m
    if load is not None:
        a["activityTrainingLoad"] = load
    return a


def _raw(activities):
    return {
        "sleep": None, "hrv": None, "summary": None, "vo2max": None,
        "activities": activities,
    }


# --- activity_sessions store: insert + read ---------------------------------

def test_insert_and_get_activity_session(sandbox):
    from runforlife.storage import metrics_store

    metrics_store.upsert_activity_session(
        "tezuesh",
        date="2026-06-10",
        activity_type="strength_training",
        start="2026-06-10T07:30:00.0",
        duration_min=45.0,
        avg_hr=128,
        max_hr=165,
        training_load=88.0,
        distance_km=None,
    )
    rows = metrics_store.get_activity_sessions("tezuesh", "2026-06-01", "2026-06-30")
    assert len(rows) == 1
    row = rows[0]
    assert row["activity_type"] == "strength_training"
    assert row["duration_min"] == 45.0
    assert row["avg_hr"] == 128
    assert row["max_hr"] == 165
    assert row["training_load"] == 88.0
    assert row["distance_km"] is None


def test_activity_session_upsert_is_idempotent(sandbox):
    """Re-ingesting the same (user, date, type, start) updates, not duplicates."""
    from runforlife.storage import metrics_store

    for load in (80.0, 95.0):
        metrics_store.upsert_activity_session(
            "tezuesh", date="2026-06-10", activity_type="strength_training",
            start="2026-06-10T07:30:00.0", duration_min=45.0, avg_hr=128,
            max_hr=165, training_load=load, distance_km=None,
        )
    rows = metrics_store.get_activity_sessions("tezuesh", "2026-06-01", "2026-06-30")
    assert len(rows) == 1
    assert rows[0]["training_load"] == 95.0  # updated to latest


def test_get_activity_sessions_respects_date_window(sandbox):
    from runforlife.storage import metrics_store

    for date in ("2026-05-01", "2026-06-10", "2026-07-01"):
        metrics_store.upsert_activity_session(
            "tezuesh", date=date, activity_type="strength_training",
            start=f"{date}T07:30:00.0", duration_min=30.0, avg_hr=120,
            max_hr=150, training_load=50.0, distance_km=None,
        )
    rows = metrics_store.get_activity_sessions("tezuesh", "2026-06-01", "2026-06-30")
    assert [r["date"] for r in rows] == ["2026-06-10"]


# --- ingest: non-running activities are persisted ---------------------------

def test_strength_activity_persisted_via_build_document(sandbox):
    from runforlife.storage import metrics_store
    from runforlife.sync.ingest import _build_document

    raw = _raw([_activity("strength_training", dur_sec=2700, hr=130,
                           max_hr=168, load=88.0)])
    doc = _build_document("tezuesh", "2026-06-10", raw)

    # Running fields untouched — this was NOT a run.
    assert doc.ran_today is False
    assert doc.run_distance_km is None

    rows = metrics_store.get_activity_sessions("tezuesh", "2026-06-01", "2026-06-30")
    assert len(rows) == 1
    assert rows[0]["activity_type"] == "strength_training"
    assert rows[0]["duration_min"] == 45.0  # 2700 sec
    assert rows[0]["avg_hr"] == 130
    assert rows[0]["training_load"] == 88.0


def test_running_activity_not_duplicated_into_activity_sessions(sandbox):
    """Running stays in daily_metrics; it must NOT also land in activity_sessions."""
    from runforlife.storage import metrics_store
    from runforlife.sync.ingest import _build_document

    raw = _raw([_activity("running", dist_m=5000)])
    raw["activities"][0]["averageSpeed"] = 2.8
    raw["activities"][0]["aerobicTrainingEffect"] = 2.5
    doc = _build_document("tezuesh", "2026-06-10", raw)

    # Existing run_* aggregation unchanged.
    assert doc.ran_today is True
    assert doc.run_distance_km == 5.0

    rows = metrics_store.get_activity_sessions("tezuesh", "2026-06-01", "2026-06-30")
    assert rows == []


def test_mixed_day_stores_run_and_strength(sandbox):
    """A day with both a run and strength: run in run_* fields, strength in sessions."""
    from runforlife.storage import metrics_store
    from runforlife.sync.ingest import _build_document

    run = _activity("running", dist_m=8000)
    run["averageSpeed"] = 2.9
    run["averageHR"] = 145
    strength = _activity("strength_training", dur_sec=3000, hr=125,
                         max_hr=160, load=70.0,
                         start="2026-06-10T18:00:00.0")
    doc = _build_document("tezuesh", "2026-06-10", _raw([run, strength]))

    # Run aggregation intact.
    assert doc.ran_today is True
    assert doc.run_distance_km == 8.0
    assert doc.run_avg_hr == 145

    # Strength captured separately.
    rows = metrics_store.get_activity_sessions("tezuesh", "2026-06-01", "2026-06-30")
    assert len(rows) == 1
    assert rows[0]["activity_type"] == "strength_training"
    assert rows[0]["duration_min"] == 50.0  # 3000 sec
    assert rows[0]["training_load"] == 70.0


def test_multiple_non_running_activities_all_stored(sandbox):
    from runforlife.storage import metrics_store
    from runforlife.sync.ingest import _build_document

    acts = [
        _activity("strength_training", start="2026-06-10T07:00:00.0"),
        _activity("indoor_cardio", start="2026-06-10T08:00:00.0"),
        _activity("cycling", dist_m=20000, start="2026-06-10T17:00:00.0"),
    ]
    _build_document("tezuesh", "2026-06-10", _raw(acts))

    rows = metrics_store.get_activity_sessions("tezuesh", "2026-06-01", "2026-06-30")
    types = sorted(r["activity_type"] for r in rows)
    assert types == ["cycling", "indoor_cardio", "strength_training"]
    cycling = next(r for r in rows if r["activity_type"] == "cycling")
    assert cycling["distance_km"] == 20.0


def test_no_activities_persists_nothing(sandbox):
    from runforlife.storage import metrics_store
    from runforlife.sync.ingest import _build_document

    _build_document("tezuesh", "2026-06-10", _raw([]))
    assert metrics_store.get_activity_sessions("tezuesh", "2026-06-01", "2026-06-30") == []


# --- hyrox stations read helper (safe on missing data) ----------------------

def test_hyrox_stations_empty_when_absent(sandbox):
    from runforlife.storage import profile_store

    # Seed profile has no 'stations' under hyrox goal.
    assert profile_store.get_hyrox_stations("tezuesh") == {}


def test_hyrox_stations_returned_when_present(sandbox):
    from runforlife.storage import profile_store

    profile = profile_store.load_profile("tezuesh")
    profile["goals"]["hyrox"]["stations"] = {
        "ski_erg": {"target_sec": 220, "pb_sec": 235},
    }
    profile_store.save_profile("tezuesh", profile)

    stations = profile_store.get_hyrox_stations("tezuesh")
    assert stations["ski_erg"]["target_sec"] == 220
