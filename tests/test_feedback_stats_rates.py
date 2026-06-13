"""
Tests for feedback_stats success/adherence rate computation and rating
normalization.

The aggregate() function must:
  - normalize free-text ratings to a small enum (positive/neutral/negative) so
    typos/casing don't fragment buckets,
  - count unrecognized ratings separately (rather than silently dropping them),
  - compute an explicit per-advice-type success_rate (positive vs negative,
    neutral excluded from the denominator) and adherence_rate.

Fully sandboxed: RUNFORLIFE_HOME is redirected to a tmp dir, so no real athlete
data is read or written. Feedback is seeded via athlete_memory.add_feedback.
"""

import importlib.util
from pathlib import Path

import pytest


@pytest.fixture()
def sandbox_home(tmp_path, monkeypatch):
    """Point all athlete storage at a throwaway tmp dir."""
    from runforlife.storage import paths

    fake_home = tmp_path / ".runforlife"
    monkeypatch.setattr(paths, "RUNFORLIFE_HOME", fake_home)
    return fake_home


@pytest.fixture()
def feedback_stats():
    """Import the feedback_stats script by path (it lives outside the package)."""
    stats_path = (
        Path(__file__).resolve().parents[1]
        / "runforlife-coach" / "scripts" / "feedback_stats.py"
    )
    spec = importlib.util.spec_from_file_location("feedback_stats", stats_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_success_rate_excludes_neutral_from_denominator(sandbox_home, feedback_stats):
    from runforlife.storage import athlete_memory

    # 2 positive, 1 negative, 1 neutral -> success_rate = 2/3 (neutral excluded)
    athlete_memory.add_feedback("tezuesh", advice_type="tempo", advice="a", rating="positive")
    athlete_memory.add_feedback("tezuesh", advice_type="tempo", advice="b", rating="positive")
    athlete_memory.add_feedback("tezuesh", advice_type="tempo", advice="c", rating="negative")
    athlete_memory.add_feedback("tezuesh", advice_type="tempo", advice="d", rating="neutral")

    result = feedback_stats.aggregate("tezuesh")
    bucket = result["by_advice_type"]["tempo"]

    assert bucket["n"] == 4
    assert bucket["ratings_normalized"] == {"positive": 2, "negative": 1, "neutral": 1}
    assert bucket["success_rate"] == pytest.approx(2 / 3)
    # rated denominator counts positive+negative only
    assert bucket["rated_n"] == 3


def test_rating_normalization_collapses_typos_and_casing(sandbox_home, feedback_stats):
    from runforlife.storage import athlete_memory

    # Various spellings/casings of "positive" must collapse into one bucket.
    athlete_memory.add_feedback("kakul", advice_type="rest", advice="a", rating="Positive")
    athlete_memory.add_feedback("kakul", advice_type="rest", advice="b", rating="POSITIVE")
    athlete_memory.add_feedback("kakul", advice_type="rest", advice="c", rating="pos")
    athlete_memory.add_feedback("kakul", advice_type="rest", advice="d", rating="good")

    result = feedback_stats.aggregate("kakul")
    bucket = result["by_advice_type"]["rest"]

    assert bucket["ratings_normalized"].get("positive") == 4
    assert bucket["success_rate"] == pytest.approx(1.0)
    assert bucket["unrecognized_ratings"] == {}


def test_unrecognized_ratings_counted_not_dropped(sandbox_home, feedback_stats):
    from runforlife.storage import athlete_memory

    athlete_memory.add_feedback("tezuesh", advice_type="deload", advice="a", rating="positive")
    athlete_memory.add_feedback("tezuesh", advice_type="deload", advice="b", rating="meh-ish")
    athlete_memory.add_feedback("tezuesh", advice_type="deload", advice="c", rating="???")

    result = feedback_stats.aggregate("tezuesh")
    bucket = result["by_advice_type"]["deload"]

    assert bucket["n"] == 3
    # The two garbage ratings are surfaced, not silently dropped.
    assert bucket["unrecognized_ratings"] == {"meh-ish": 1, "???": 1}
    # success_rate based only on recognized positive/negative: 1 positive, 0 negative
    assert bucket["success_rate"] == pytest.approx(1.0)
    assert bucket["rated_n"] == 1


def test_success_rate_none_when_no_rated_feedback(sandbox_home, feedback_stats):
    from runforlife.storage import athlete_memory

    # Only neutral + unrecognized -> no positive/negative signal -> success_rate None.
    athlete_memory.add_feedback("kakul", advice_type="tempo", advice="a", rating="neutral")
    athlete_memory.add_feedback("kakul", advice_type="tempo", advice="b", rating="whoknows")

    result = feedback_stats.aggregate("kakul")
    bucket = result["by_advice_type"]["tempo"]

    assert bucket["success_rate"] is None
    assert bucket["rated_n"] == 0


def test_adherence_rate_followed_over_known(sandbox_home, feedback_stats):
    from runforlife.storage import athlete_memory

    # 2 followed, 1 partial, 1 ignored -> adherence_rate counts "followed" as 1.0,
    # "partial" as 0.5, "ignored" as 0.0 over known-adherence rows = (1+1+0.5+0)/4.
    athlete_memory.add_feedback(
        "tezuesh", advice_type="long_run", advice="a", rating="positive", adherence="followed"
    )
    athlete_memory.add_feedback(
        "tezuesh", advice_type="long_run", advice="b", rating="positive", adherence="followed"
    )
    athlete_memory.add_feedback(
        "tezuesh", advice_type="long_run", advice="c", rating="neutral", adherence="partial"
    )
    athlete_memory.add_feedback(
        "tezuesh", advice_type="long_run", advice="d", rating="negative", adherence="ignored"
    )

    result = feedback_stats.aggregate("tezuesh")
    bucket = result["by_advice_type"]["long_run"]

    assert bucket["adherence_n"] == 4
    assert bucket["adherence_rate"] == pytest.approx((1 + 1 + 0.5 + 0) / 4)


def test_adherence_rate_none_when_no_adherence(sandbox_home, feedback_stats):
    from runforlife.storage import athlete_memory

    athlete_memory.add_feedback("kakul", advice_type="rest", advice="a", rating="positive")

    result = feedback_stats.aggregate("kakul")
    bucket = result["by_advice_type"]["rest"]

    assert bucket["adherence_rate"] is None
    assert bucket["adherence_n"] == 0


def test_legacy_keys_preserved(sandbox_home, feedback_stats):
    """Backward compatibility: original JSON keys must still be present."""
    from runforlife.storage import athlete_memory

    athlete_memory.add_feedback(
        "tezuesh", advice_type="tempo", advice="a", rating="positive",
        adherence="followed", outcome="hit target pace",
    )

    result = feedback_stats.aggregate("tezuesh")
    assert result["user"] == "tezuesh"
    assert result["total_feedback"] == 1
    assert result["advice_types"] == 1
    bucket = result["by_advice_type"]["tempo"]
    # original keys
    assert bucket["n"] == 1
    assert "ratings" in bucket
    assert "adherence" in bucket
    assert bucket["sample_outcomes"] == ["hit target pace"]
