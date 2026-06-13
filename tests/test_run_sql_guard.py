"""
Tests for the read-only guard in the run_sql analysis skill.

The old guard was prefix-only: it accepted anything that *started* with SELECT
(after stripping leading parens/whitespace). That let CTE-wrapped writes
("WITH x AS (...) DELETE ...") and multi-statement payloads
("SELECT 1; DROP TABLE x") through. These tests pin the tightened behaviour:

  - a plain SELECT passes
  - a CTE + SELECT ("WITH ... SELECT") passes
  - a CTE + DELETE is rejected
  - a multi-statement "SELECT 1; DROP TABLE x" is rejected

Fully sandboxed: RUNFORLIFE_HOME is redirected to a tmp dir and a tiny
daily_metrics table is seeded, so no real athlete data is read or written.
"""

import sqlite3

import pytest


@pytest.fixture()
def sandbox_home(tmp_path, monkeypatch):
    """Point all athlete storage at a throwaway tmp dir."""
    from runforlife.storage import paths

    monkeypatch.setattr(paths, "RUNFORLIFE_HOME", tmp_path / ".runforlife")
    return tmp_path


@pytest.fixture()
def seeded_db(sandbox_home):
    """Create a minimal daily_metrics table for 'tezuesh' so SELECTs can run."""
    from runforlife.storage.paths import metrics_db_path

    db_path = metrics_db_path("tezuesh")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE daily_metrics ("
        "user_id TEXT, date TEXT, run_distance_km REAL)"
    )
    conn.execute(
        "INSERT INTO daily_metrics VALUES ('tezuesh', '2026-06-01', 5.0)"
    )
    conn.commit()
    conn.close()
    return db_path


def _run(sql: str) -> dict:
    from runforlife.skills.analysis.run_sql import RunSQL

    return RunSQL().execute(user="tezuesh", sql=sql)


def test_plain_select_passes(seeded_db):
    result = _run("SELECT date, run_distance_km FROM daily_metrics WHERE user_id = ?")
    assert result["success"] is True
    assert result["row_count"] == 1
    assert result["rows"][0]["run_distance_km"] == 5.0


def test_cte_then_select_passes(seeded_db):
    sql = (
        "WITH runs AS ("
        "  SELECT run_distance_km FROM daily_metrics WHERE user_id = ?"
        ") SELECT COUNT(*) AS n FROM runs"
    )
    result = _run(sql)
    assert result["success"] is True
    assert result["rows"][0]["n"] == 1


def test_cte_then_delete_is_rejected(seeded_db):
    sql = (
        "WITH x AS (SELECT 1) "
        "DELETE FROM daily_metrics WHERE user_id = ?"
    )
    result = _run(sql)
    assert result["success"] is False
    assert "SELECT" in result["error"]
    # The table must be untouched.
    conn = sqlite3.connect(str(seeded_db))
    remaining = conn.execute("SELECT COUNT(*) FROM daily_metrics").fetchone()[0]
    conn.close()
    assert remaining == 1


def test_multi_statement_with_drop_is_rejected(seeded_db):
    result = _run("SELECT 1; DROP TABLE daily_metrics")
    assert result["success"] is False
    # The table must still exist.
    conn = sqlite3.connect(str(seeded_db))
    exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='daily_metrics'"
    ).fetchone()
    conn.close()
    assert exists is not None


def test_trailing_semicolon_single_statement_passes(seeded_db):
    """A single SELECT with a trailing semicolon is still legitimate read-only."""
    result = _run("SELECT run_distance_km FROM daily_metrics WHERE user_id = ?;")
    assert result["success"] is True
    assert result["row_count"] == 1


def test_delete_prefix_is_rejected(seeded_db):
    result = _run("DELETE FROM daily_metrics WHERE user_id = ?")
    assert result["success"] is False
