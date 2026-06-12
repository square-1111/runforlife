"""
Tests for the feedback capture step (the fix for an always-empty feedback.json).

Verifies athlete_memory.add_feedback persists a well-formed record that
feedback_stats.aggregate then tallies — i.e. the /reflect loop now has fuel.

Fully sandboxed: RUNFORLIFE_HOME is redirected to a tmp dir, so no real athlete
data is read or written.
"""

from pathlib import Path

import pytest


@pytest.fixture()
def sandbox_home(tmp_path, monkeypatch):
    """Point all athlete storage at a throwaway tmp dir."""
    from runforlife.storage import paths

    fake_home = tmp_path / ".runforlife"
    monkeypatch.setattr(paths, "RUNFORLIFE_HOME", fake_home)
    return fake_home


def test_add_feedback_persists_record(sandbox_home):
    from runforlife.storage import athlete_memory

    new_id = athlete_memory.add_feedback(
        "tezuesh",
        advice_type="deload",
        advice="Skip Push, easy 3km",
        rating="positive",
        adherence="followed",
        outcome="felt fresh next day, HRV up",
    )
    assert new_id == 1

    items = athlete_memory.load_feedback("tezuesh")
    assert len(items) == 1
    record = items[0]
    assert record["advice_type"] == "deload"
    assert record["rating"] == "positive"
    assert record["adherence"] == "followed"
    assert "date" in record


def test_ids_autoincrement(sandbox_home):
    from runforlife.storage import athlete_memory

    a = athlete_memory.add_feedback("kakul", advice_type="tempo", advice="x", rating="positive")
    b = athlete_memory.add_feedback("kakul", advice_type="rest", advice="y", rating="negative")
    assert (a, b) == (1, 2)


def test_feedback_stats_tallies_captured_records(sandbox_home):
    """End-to-end: capture two records, then the reflect reader counts them."""
    from runforlife.storage import athlete_memory

    athlete_memory.add_feedback("tezuesh", advice_type="deload", advice="a", rating="positive")
    athlete_memory.add_feedback("tezuesh", advice_type="deload", advice="b", rating="negative")
    athlete_memory.add_feedback("tezuesh", advice_type="tempo", advice="c", rating="positive")

    # Import the feedback_stats script by path and aggregate.
    import importlib.util

    stats_path = (
        Path(__file__).resolve().parents[1]
        / "runforlife-coach" / "scripts" / "feedback_stats.py"
    )
    spec = importlib.util.spec_from_file_location("feedback_stats", stats_path)
    feedback_stats = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(feedback_stats)

    result = feedback_stats.aggregate("tezuesh")
    assert result["total_feedback"] == 3
    assert result["advice_types"] == 2
    assert result["by_advice_type"]["deload"]["n"] == 2
    assert result["by_advice_type"]["deload"]["ratings"] == {"positive": 1, "negative": 1}
