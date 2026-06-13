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

# Non-running activities (strength_training, SkiErg, sled, HIIT, cycling, …).
# The daily_metrics table is run-centric and silently drops these, hiding all
# Hyrox / strength load. This sibling table captures them WITHOUT touching the
# existing running aggregation. Keyed by (user_id, date, activity_type, start)
# so the same session re-ingested on a --resync updates rather than duplicates.
_CREATE_ACTIVITY_SESSIONS = """\
CREATE TABLE IF NOT EXISTS activity_sessions (
    user_id        TEXT    NOT NULL,
    date           TEXT    NOT NULL,
    activity_type  TEXT    NOT NULL,
    start          TEXT    NOT NULL,
    duration_min   REAL,
    avg_hr         INTEGER,
    max_hr         INTEGER,
    training_load  REAL,
    distance_km    REAL,
    created_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, date, activity_type, start)
)
"""

_CREATE_ACTIVITY_SESSIONS_INDEX = """\
CREATE INDEX IF NOT EXISTS idx_activity_sessions_user_date
ON activity_sessions (user_id, date)
"""

# Per-lap/split detail for RUN activities. The daily_metrics table stores ONLY
# the daily run aggregate (total distance, avg pace, avg HR) — which discards the
# rep-by-rep structure of an interval workout. This sibling table captures each
# lap of the MAIN run so the July interval block's rep-level pace/HR is persisted.
# Keyed by (user_id, date, activity_id, lap_index) so a --resync of the same
# activity updates each lap rather than duplicating. Additive: it never touches
# the run_* fields or the daily aggregation.
_CREATE_RUN_LAPS = """\
CREATE TABLE IF NOT EXISTS run_laps (
    user_id              TEXT    NOT NULL,
    date                 TEXT    NOT NULL,
    activity_id          TEXT    NOT NULL,
    lap_index            INTEGER NOT NULL,
    distance_km          REAL,
    duration_sec         REAL,
    avg_pace_sec_per_km  REAL,
    avg_hr               INTEGER,
    max_hr               INTEGER,
    created_at           TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, date, activity_id, lap_index)
)
"""

_CREATE_RUN_LAPS_INDEX = """\
CREATE INDEX IF NOT EXISTS idx_run_laps_user_date
ON run_laps (user_id, date)
"""

# All columns added after initial schema — migrated safely via ALTER TABLE
_MIGRATION_COLUMNS = [
    # Subjective check-in (added first)
    ("subjective_readiness",  "INTEGER"),
    ("life_context_note",     "TEXT"),
    ("session_rpe",           "INTEGER"),
    # Sleep detail
    ("deep_sleep_min",        "INTEGER"),
    ("rem_sleep_min",         "INTEGER"),
    ("light_sleep_min",       "INTEGER"),
    ("sleep_start_local",     "TEXT"),
    ("sleep_hr_avg",          "INTEGER"),
    ("respiration_avg",       "REAL"),
    # HRV enrichment
    ("hrv_weekly_avg",        "INTEGER"),
    ("hrv_5min_high",         "INTEGER"),
    ("hrv_baseline_low",      "INTEGER"),
    ("hrv_baseline_high",     "INTEGER"),
    ("hrv_garmin_status",     "TEXT"),
    # Body battery detail
    ("body_battery_morning",  "INTEGER"),
    ("body_battery_peak",     "INTEGER"),
    # Stress detail
    ("stress_max",            "INTEGER"),
    ("stress_qualifier",      "TEXT"),
    # Activity
    ("steps",                 "INTEGER"),
    ("active_calories",       "INTEGER"),
    # Fitness
    ("vo2_max",               "REAL"),
    # Run environment (heat / treadmill confounders for pace & EF analytics)
    ("run_is_indoor",         "INTEGER"),
    ("run_temp_c",            "REAL"),
    # Aerobic efficiency (speed/HR) — the base-builder's progress signal
    ("run_efficiency_factor", "REAL"),
]


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
        conn.execute(_CREATE_ACTIVITY_SESSIONS)
        conn.execute(_CREATE_ACTIVITY_SESSIONS_INDEX)
        conn.execute(_CREATE_RUN_LAPS)
        conn.execute(_CREATE_RUN_LAPS_INDEX)
        for col, defn in _MIGRATION_COLUMNS:
            try:
                conn.execute(f"ALTER TABLE daily_metrics ADD COLUMN {col} {defn}")
            except sqlite3.OperationalError:
                pass  # column already exists
        conn.commit()
        yield conn
    finally:
        conn.close()


def upsert_day(user: str, doc: "DailyDocument") -> None:
    """Insert or update a day's metrics row.

    Uses an UPSERT scoped to the columns the document actually owns (Garmin +
    computed features). Columns NOT in to_row() — the manually-entered
    subjective_readiness / life_context_note / session_rpe — are left untouched
    on conflict. This is deliberate: the old INSERT OR REPLACE deleted the whole
    row and re-inserted, silently wiping subjective check-ins on every --resync.
    """
    row = doc.to_row()
    cols = list(row.keys())
    col_names = ", ".join(cols)
    placeholders = ", ".join("?" * len(cols))
    # On conflict, update every owned column except the primary key.
    update_cols = [c for c in cols if c not in ("user_id", "date")]
    update_clause = ", ".join(f"{c} = excluded.{c}" for c in update_cols)
    with _conn(user) as conn:
        conn.execute(
            f"INSERT INTO daily_metrics ({col_names}) VALUES ({placeholders}) "
            f"ON CONFLICT(user_id, date) DO UPDATE SET {update_clause}",
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
    """Check whether a row exists for this date (existence only)."""
    with _conn(user) as conn:
        row = conn.execute(
            "SELECT 1 FROM daily_metrics WHERE user_id = ? AND date = ?",
            (user, date),
        ).fetchone()
    return row is not None


# Garmin-sourced signals that prove a day was actually synced (not a skeleton
# row left behind by a subjective check-in or a partial/failed fetch). If a row
# exists but ALL of these are NULL/absent, it's incomplete and must be re-ingested.
_COMPLETENESS_SIGNALS = (
    "resting_hr",
    "sleep_duration_min",
    "hrv_last_night",
    "steps",
    "body_battery_morning",
)


def has_complete_day(user: str, date: str) -> bool:
    """Whether this date has a row with real Garmin data (not a skeleton).

    Returns False when no row exists OR the row is a skeleton (all completeness
    signals NULL and no run logged) — the case the old existence-only `has_day`
    skip check kept skipping forever, permanently hiding real runs. The nightly
    skip path uses this so incomplete rows get re-ingested automatically.
    """
    signal_cols = ", ".join(_COMPLETENESS_SIGNALS)
    with _conn(user) as conn:
        row = conn.execute(
            f"SELECT ran_today, {signal_cols} FROM daily_metrics "
            "WHERE user_id = ? AND date = ?",
            (user, date),
        ).fetchone()
    if row is None:
        return False
    if row["ran_today"]:
        return True
    return any(row[col] is not None for col in _COMPLETENESS_SIGNALS)


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


def upsert_subjective(
    user: str,
    date: str,
    readiness: int,
    context: str,
    rpe: int | None = None,
) -> None:
    """Save today's subjective check-in. Creates a skeleton row if none exists."""
    with _conn(user) as conn:
        # Ensure row exists (INSERT OR IGNORE preserves existing Garmin data)
        conn.execute(
            "INSERT OR IGNORE INTO daily_metrics (user_id, date, ran_today) VALUES (?, ?, 0)",
            (user, date),
        )
        conn.execute(
            """UPDATE daily_metrics
               SET subjective_readiness = ?,
                   life_context_note    = ?,
                   session_rpe          = COALESCE(?, session_rpe)
               WHERE user_id = ? AND date = ?""",
            (readiness, context, rpe, user, date),
        )
        conn.commit()


def has_checkin_today(user: str, date: str) -> bool:
    """Whether today's subjective check-in has been recorded."""
    with _conn(user) as conn:
        row = conn.execute(
            "SELECT subjective_readiness FROM daily_metrics WHERE user_id = ? AND date = ?",
            (user, date),
        ).fetchone()
    return row is not None and row[0] is not None


# --- activity_sessions: non-running activities (strength, Hyrox, cycling) ----

def upsert_activity_session(
    user: str,
    date: str,
    activity_type: str,
    start: str,
    duration_min: float | None = None,
    avg_hr: int | None = None,
    max_hr: int | None = None,
    training_load: float | None = None,
    distance_km: float | None = None,
) -> None:
    """Insert or update one non-running activity session.

    Keyed by (user_id, date, activity_type, start). Re-ingesting the same
    session (e.g. on a --resync) refreshes its values rather than duplicating.
    This is a SEPARATE table from daily_metrics: it never touches the run_*
    fields or the daily wellness row.
    """
    with _conn(user) as conn:
        conn.execute(
            """
            INSERT INTO activity_sessions
                (user_id, date, activity_type, start,
                 duration_min, avg_hr, max_hr, training_load, distance_km)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, date, activity_type, start) DO UPDATE SET
                duration_min  = excluded.duration_min,
                avg_hr        = excluded.avg_hr,
                max_hr        = excluded.max_hr,
                training_load = excluded.training_load,
                distance_km   = excluded.distance_km
            """,
            (user, date, activity_type, start,
             duration_min, avg_hr, max_hr, training_load, distance_km),
        )
        conn.commit()


def get_activity_sessions(user: str, start_date: str, end_date: str) -> list[dict]:
    """Return non-running activity sessions in [start_date, end_date], oldest-first.

    Read-only friendly: callers (a future Hyrox/strength specialist) can read
    strength / SkiErg / sled / HIIT / cycling load without disturbing the run
    aggregation in daily_metrics.
    """
    with _conn(user) as conn:
        rows = conn.execute(
            """
            SELECT * FROM activity_sessions
            WHERE user_id = ? AND date >= ? AND date <= ?
            ORDER BY date ASC, start ASC
            """,
            (user, start_date, end_date),
        ).fetchall()
    return [dict(r) for r in rows]


# --- run_laps: per-lap/split detail for RUN activities ----------------------

def upsert_run_lap(
    user: str,
    date: str,
    activity_id: str,
    lap_index: int,
    distance_km: float | None = None,
    duration_sec: float | None = None,
    avg_pace_sec_per_km: float | None = None,
    avg_hr: int | None = None,
    max_hr: int | None = None,
) -> None:
    """Insert or update one lap/split of a run.

    Keyed by (user_id, date, activity_id, lap_index). Re-ingesting the same lap
    (e.g. on a --resync) refreshes its values rather than duplicating. This is a
    SEPARATE table from daily_metrics: it never touches the run_* fields or the
    daily wellness row.
    """
    with _conn(user) as conn:
        conn.execute(
            """
            INSERT INTO run_laps
                (user_id, date, activity_id, lap_index,
                 distance_km, duration_sec, avg_pace_sec_per_km, avg_hr, max_hr)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, date, activity_id, lap_index) DO UPDATE SET
                distance_km         = excluded.distance_km,
                duration_sec        = excluded.duration_sec,
                avg_pace_sec_per_km = excluded.avg_pace_sec_per_km,
                avg_hr              = excluded.avg_hr,
                max_hr              = excluded.max_hr
            """,
            (user, date, str(activity_id), lap_index,
             distance_km, duration_sec, avg_pace_sec_per_km, avg_hr, max_hr),
        )
        conn.commit()


def get_run_laps(user: str, date: str) -> list[dict]:
    """Return all stored laps for a date, ordered by activity then lap_index.

    Read-only friendly: a future interval specialist can read rep-level pace/HR
    without disturbing the run aggregation in daily_metrics.
    """
    with _conn(user) as conn:
        rows = conn.execute(
            """
            SELECT * FROM run_laps
            WHERE user_id = ? AND date = ?
            ORDER BY activity_id ASC, lap_index ASC
            """,
            (user, date),
        ).fetchall()
    return [dict(r) for r in rows]
