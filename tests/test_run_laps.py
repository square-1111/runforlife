"""
Tests for per-lap/split capture of RUN activities (RANK 15, ADDITIVE ONLY).

Today only the daily run aggregate (run_distance_km, run_avg_pace_sec_per_km,
run_avg_hr, ...) is persisted. The July interval block needs rep-level pace/HR,
so the MAIN run's laps are captured into a new sibling table run_laps WITHOUT
touching the existing daily run aggregation.

These tests pin the new behavior with MOCK Garmin split dicts (no network):
  - a parsed lap list persists to run_laps and reads back
  - multiple laps are keyed correctly by lap_index (idempotent re-ingest)
  - a run with no laps stores nothing
  - the daily run_* fields are unchanged by lap capture

All storage is redirected to a tmp dir — never touches real ~/.runforlife.
"""

import pytest


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """Redirect athlete storage to a throwaway dir."""
    from runforlife.storage import paths

    monkeypatch.setattr(paths, "RUNFORLIFE_HOME", tmp_path / ".runforlife")
    return tmp_path


def _lap(distance_m=1000.0, duration_sec=300.0, speed_mps=3.0,
         avg_hr=160, max_hr=172):
    """A mock Garmin lap dict shaped like a get_activity_splits lapDTO."""
    return {
        "distance": distance_m,
        "duration": duration_sec,
        "averageSpeed": speed_mps,
        "averageHR": avg_hr,
        "maxHR": max_hr,
    }


def _splits(laps, key="lapDTOs"):
    return {key: laps}


# --- run_laps store: insert + read ------------------------------------------

def test_insert_and_get_run_lap(sandbox):
    from runforlife.storage import metrics_store

    metrics_store.upsert_run_lap(
        "tezuesh",
        date="2026-07-10",
        activity_id="12345",
        lap_index=0,
        distance_km=1.0,
        duration_sec=300.0,
        avg_pace_sec_per_km=300.0,
        avg_hr=160,
        max_hr=172,
    )
    rows = metrics_store.get_run_laps("tezuesh", "2026-07-10")
    assert len(rows) == 1
    row = rows[0]
    assert row["activity_id"] == "12345"
    assert row["lap_index"] == 0
    assert row["distance_km"] == 1.0
    assert row["duration_sec"] == 300.0
    assert row["avg_pace_sec_per_km"] == 300.0
    assert row["avg_hr"] == 160
    assert row["max_hr"] == 172


def test_run_lap_upsert_is_idempotent(sandbox):
    """Re-ingesting the same (user, date, activity, lap_index) updates, not dups."""
    from runforlife.storage import metrics_store

    for hr in (150, 165):
        metrics_store.upsert_run_lap(
            "tezuesh", date="2026-07-10", activity_id="12345", lap_index=0,
            distance_km=1.0, duration_sec=300.0, avg_pace_sec_per_km=300.0,
            avg_hr=hr, max_hr=172,
        )
    rows = metrics_store.get_run_laps("tezuesh", "2026-07-10")
    assert len(rows) == 1
    assert rows[0]["avg_hr"] == 165  # updated to latest


def test_multiple_laps_keyed_by_index(sandbox):
    from runforlife.storage import metrics_store

    for i in range(4):
        metrics_store.upsert_run_lap(
            "tezuesh", date="2026-07-10", activity_id="12345", lap_index=i,
            distance_km=1.0, duration_sec=300.0 + i, avg_pace_sec_per_km=300.0 + i,
            avg_hr=160 + i, max_hr=170 + i,
        )
    rows = metrics_store.get_run_laps("tezuesh", "2026-07-10")
    assert [r["lap_index"] for r in rows] == [0, 1, 2, 3]
    assert rows[2]["avg_hr"] == 162


def test_get_run_laps_filters_by_date(sandbox):
    from runforlife.storage import metrics_store

    for date in ("2026-07-09", "2026-07-10"):
        metrics_store.upsert_run_lap(
            "tezuesh", date=date, activity_id="a", lap_index=0,
            distance_km=1.0, duration_sec=300.0, avg_pace_sec_per_km=300.0,
            avg_hr=160, max_hr=172,
        )
    rows = metrics_store.get_run_laps("tezuesh", "2026-07-10")
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-07-10"


# --- lap parsing (pure, mock dicts) -----------------------------------------

def test_parse_laps_from_lap_dtos(sandbox):
    from runforlife.sync.ingest import _parse_laps

    raw = _splits([
        _lap(distance_m=400.0, duration_sec=90.0, speed_mps=4.44,
             avg_hr=175, max_hr=182),
        _lap(distance_m=400.0, duration_sec=92.0, speed_mps=4.35,
             avg_hr=178, max_hr=185),
    ])
    laps = _parse_laps(raw)
    assert len(laps) == 2
    assert laps[0]["lap_index"] == 0
    assert laps[0]["distance_km"] == 0.4
    assert laps[0]["duration_sec"] == 90.0
    assert laps[0]["avg_pace_sec_per_km"] == round(1000 / 4.44)
    assert laps[0]["avg_hr"] == 175
    assert laps[0]["max_hr"] == 182
    assert laps[1]["lap_index"] == 1


def test_parse_laps_ignores_split_summaries(sandbox):
    """splitSummaries are overlapping category ROLLUPS (RWD_RUN, INTERVAL_ACTIVE,
    RWD_WALK, ...) — the same meters counted under multiple types. They are NOT
    per-lap data and must never be ingested as laps (that double-counted the
    distance ~2x). Only lapDTOs from get_activity_splits are real laps.
    """
    from runforlife.sync.ingest import _parse_laps

    raw = _splits([_lap(), _lap()], key="splitSummaries")
    assert _parse_laps(raw) == []


def test_parse_laps_empty_when_no_laps(sandbox):
    from runforlife.sync.ingest import _parse_laps

    assert _parse_laps({}) == []
    assert _parse_laps({"lapDTOs": []}) == []
    assert _parse_laps(None) == []


def test_parse_laps_pace_none_when_no_speed(sandbox):
    from runforlife.sync.ingest import _parse_laps

    raw = _splits([_lap(speed_mps=0)])
    laps = _parse_laps(raw)
    assert laps[0]["avg_pace_sec_per_km"] is None


# --- persist run laps end-to-end (mock splits, no network) ------------------

def test_persist_run_laps_stores_parsed_laps(sandbox):
    from runforlife.storage import metrics_store
    from runforlife.sync.ingest import _persist_run_laps

    raw = _splits([
        _lap(distance_m=400.0, duration_sec=90.0, speed_mps=4.44, avg_hr=175),
        _lap(distance_m=400.0, duration_sec=92.0, speed_mps=4.35, avg_hr=178),
        _lap(distance_m=200.0, duration_sec=60.0, speed_mps=3.33, avg_hr=150),
    ])
    _persist_run_laps("tezuesh", "2026-07-10", "9999", raw)

    rows = metrics_store.get_run_laps("tezuesh", "2026-07-10")
    assert len(rows) == 3
    assert all(r["activity_id"] == "9999" for r in rows)
    assert [r["lap_index"] for r in rows] == [0, 1, 2]
    assert rows[0]["avg_hr"] == 175


def test_persist_run_laps_no_laps_stores_nothing(sandbox):
    from runforlife.storage import metrics_store
    from runforlife.sync.ingest import _persist_run_laps

    _persist_run_laps("tezuesh", "2026-07-10", "9999", {"lapDTOs": []})
    assert metrics_store.get_run_laps("tezuesh", "2026-07-10") == []

    _persist_run_laps("tezuesh", "2026-07-10", "9999", None)
    assert metrics_store.get_run_laps("tezuesh", "2026-07-10") == []


def test_persist_run_laps_requires_activity_id(sandbox):
    from runforlife.storage import metrics_store
    from runforlife.sync.ingest import _persist_run_laps

    _persist_run_laps("tezuesh", "2026-07-10", None, _splits([_lap()]))
    assert metrics_store.get_run_laps("tezuesh", "2026-07-10") == []


# --- daily run_* aggregation is UNCHANGED by lap capture --------------------

def _activity(type_key="running", dist_m=5000, dur_sec=1800, hr=145,
              max_hr=170, speed=2.8, te=2.5, activity_id="555",
              start="2026-07-10T07:30:00.0"):
    a = {
        "activityType": {"typeKey": type_key},
        "duration": dur_sec,
        "averageHR": hr,
        "maxHR": max_hr,
        "averageSpeed": speed,
        "aerobicTrainingEffect": te,
        "startTimeLocal": start,
        "activityId": activity_id,
    }
    if dist_m is not None:
        a["distance"] = dist_m
    return a


def _raw(activities):
    return {
        "sleep": None, "hrv": None, "summary": None, "vo2max": None,
        "activities": activities,
    }


def test_build_document_run_aggregation_unchanged(sandbox):
    """Lap capture must not alter the existing daily run_* fields."""
    from runforlife.sync.ingest import _build_document

    doc = _build_document("tezuesh", "2026-07-10", _raw([_activity()]))

    assert doc.ran_today is True
    assert doc.run_distance_km == 5.0
    assert doc.run_avg_hr == 145
    assert doc.run_avg_pace_sec_per_km == round(1000 / 2.8)
    assert doc.training_effect_aerobic == 2.5


def test_build_document_does_not_fetch_laps(sandbox):
    """_build_document stays network-free: it must NOT call the garmin client.

    Lap fetching is wired in the collector/ingest layer, not the pure builder.
    A run with no pre-fetched splits leaves run_laps empty after build.
    """
    from runforlife.storage import metrics_store
    from runforlife.sync.ingest import _build_document

    _build_document("tezuesh", "2026-07-10", _raw([_activity()]))
    assert metrics_store.get_run_laps("tezuesh", "2026-07-10") == []
