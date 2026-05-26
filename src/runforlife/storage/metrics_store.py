"""
SQLite store for daily training metrics.

One row per user per day. Replaces the Chroma vector store for all
numeric querying — injury risk, correlations, historical windows,
and pattern recall all read from here.
"""

import sqlite3
from contextlib import contextmanager
from typing import TYPE_CHECKING, Generator

from runforlife.storage.paths import metrics_db_path

if TYPE_CHECKING:
    from runforlife.rag.daily_document import DailyDocument

_CREATE_TABLE = """\
CREATE TABLE IF NOT EXISTS daily_metrics (
    user_id                  TEXT    NOT NULL,
    date                     TEXT    NOT NULL,
    sleep_duration_min       REAL,
    sleep_score              INTEGER,
    sleep_efficiency         REAL,
    hrv_last_night           REAL,
    resting_hr               INTEGER,
    readiness_score          INTEGER,
    body_battery_end         INTEGER,
    stress_avg               INTEGER,
    ran_today                INTEGER NOT NULL DEFAULT 0,
    run_distance_km          REAL,
    run_avg_pace_sec_per_km  REAL,
    run_avg_hr               INTEGER,
    training_effect_aerobic  REAL,
    acwr                     REAL,
    hrv_7d_slope             REAL,
    sleep_efficiency_delta   REAL,
    rhr_7d_slope             REAL,
    created_at               TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, date)
)
"""

_CREATE_INDEX = """\
CREATE INDEX IF NOT EXISTS idx_daily_metrics_user_date
ON daily_metrics (user_id, date)
"""


@contextmanager
def _conn(user: str) -> Generator[sqlite3.Connection, None, None]:
    db_path = metrics_db_path(user)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    try:
        conn.execute(_CREATE_TABLE)
        conn.execute(_CREATE_INDEX)
        conn.commit()
        yield conn
    finally:
        conn.close()


def upsert_day(user: str, doc: "DailyDocument") -> None:
    """Insert or replace a day's metrics row."""
    row = doc.to_row()
    cols = list(row.keys())
    col_names = ", ".join(cols)
    placeholders = ", ".join("?" * len(cols))
    with _conn(user) as conn:
        conn.execute(
            f"INSERT OR REPLACE INTO daily_metrics ({col_names}) VALUES ({placeholders})",
            [row[c] for c in cols],
        )
        conn.commit()


def get_day(user: str, date: str) -> dict | None:
    """Return a single day's row, or None if not found."""
    with _conn(user) as conn:
        row = conn.execute(
            "SELECT * FROM daily_metrics WHERE user_id = ? AND date = ?",
            (user, date),
        ).fetchone()
    return dict(row) if row else None


def get_window(user: str, end_date: str, days: int) -> list[dict]:
    """
    Return up to `days` rows ending on end_date, ordered oldest-first.

    Used by feature computation (HRV slope, sleep delta) and skill queries.
    Missing days have no row — result length may be less than `days`.
    """
    with _conn(user) as conn:
        rows = conn.execute(
            """
            SELECT * FROM daily_metrics
            WHERE user_id = ? AND date <= ?
            ORDER BY date DESC
            LIMIT ?
            """,
            (user, end_date, days),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def has_day(user: str, date: str) -> bool:
    """Check whether a row exists for this date."""
    with _conn(user) as conn:
        row = conn.execute(
            "SELECT 1 FROM daily_metrics WHERE user_id = ? AND date = ?",
            (user, date),
        ).fetchone()
    return row is not None


def get_recent(user: str, n: int = 30) -> list[dict]:
    """Return the most recent n rows, newest-first."""
    with _conn(user) as conn:
        rows = conn.execute(
            "SELECT * FROM daily_metrics WHERE user_id = ? ORDER BY date DESC LIMIT ?",
            (user, n),
        ).fetchall()
    return [dict(r) for r in rows]


def count_days(user: str) -> int:
    """Total number of synced days for this user."""
    with _conn(user) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM daily_metrics WHERE user_id = ?",
            (user,),
        ).fetchone()
    return row[0] if row else 0
