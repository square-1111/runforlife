"""
Dynamic SQL fallback — execute any SELECT against the daily_metrics table.

When fixed skills can't answer an analytical question, this skill lets
Claude write SQL directly. Covers one-off queries that don't justify a
dedicated skill: fastest day-of-week, longest streak ever, best 4-week
block, custom date range aggregations.

Safety: only SELECT statements are permitted.
"""

import re
import sqlite3
from typing import Any

from runforlife.skills.base import Skill
from runforlife.storage.paths import metrics_db_path

# Statements a read-only query may legitimately start with.
_READ_ONLY_PREFIXES = ("SELECT", "WITH")
# Write/DDL keywords that must never appear as a statement verb — even when
# hidden behind a CTE ("WITH x AS (...) DELETE ...").
_WRITE_KEYWORDS = (
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
    "REPLACE", "TRUNCATE", "ATTACH", "DETACH", "PRAGMA",
    "REINDEX", "VACUUM", "GRANT", "REVOKE", "MERGE", "UPSERT",
)


def _strip_sql_comments(sql: str) -> str:
    """Remove -- line comments and /* */ block comments."""
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return sql


def _is_read_only(sql: str) -> tuple[bool, str]:
    """Return (ok, reason). Allows a single SELECT or WITH...SELECT statement.

    Rejects:
      - multi-statement payloads ("SELECT 1; DROP TABLE x")
      - CTE-wrapped writes ("WITH x AS (...) DELETE ...")
      - any statement whose verb is a write/DDL keyword
    Allows a single trailing semicolon (a lone read-only statement).
    """
    cleaned = _strip_sql_comments(sql).strip()
    if not cleaned:
        return False, "Empty query."

    # Reject multi-statement payloads. A single trailing ';' is fine; any
    # non-empty content after a ';' means a second statement.
    without_trailing = cleaned.rstrip(";").strip()
    if ";" in without_trailing:
        return False, "Only a single SELECT statement is permitted (no ';')."

    upper = without_trailing.upper()
    first_word = re.match(r"\s*([A-Z_]+)", upper)
    if not first_word or first_word.group(1) not in _READ_ONLY_PREFIXES:
        return False, "Only SELECT queries are permitted."

    # Even a WITH/SELECT prefix can hide a write verb after the CTE body, e.g.
    # "WITH x AS (...) DELETE ...". Reject any write keyword that appears as a
    # standalone word anywhere in the statement.
    for keyword in _WRITE_KEYWORDS:
        if re.search(rf"\b{keyword}\b", upper):
            return False, "Only SELECT queries are permitted (write keyword found)."

    return True, ""

_SCHEMA_HINT = """\
Table: daily_metrics
Columns:
  user_id TEXT, date TEXT (YYYY-MM-DD),
  sleep_score INTEGER, sleep_efficiency REAL, sleep_duration_min REAL,
  hrv_last_night REAL, resting_hr INTEGER,
  readiness_score INTEGER, body_battery_end INTEGER, stress_avg INTEGER,
  ran_today INTEGER (0/1), run_distance_km REAL,
  run_avg_pace_sec_per_km REAL, run_avg_hr INTEGER,
  acwr REAL, hrv_7d_slope REAL, sleep_efficiency_delta REAL, rhr_7d_slope REAL
Always include WHERE user_id = ? and pass the user as the parameter."""


class RunSQL(Skill):
    name = "run_sql"

    description = (
        "Execute a SQL SELECT query against the athlete's daily_metrics table. "
        "Use as a fallback for analytical questions the fixed skills don't cover: "
        "custom aggregations, day-of-week patterns, all-time records, "
        "streak detection, multi-condition filters. "
        f"{_SCHEMA_HINT} "
        "Only SELECT queries are allowed. Use ? as placeholder for user_id."
    )

    input_schema = {
        "type": "object",
        "properties": {
            "user": {
                "type": "string",
                "enum": ["tezuesh", "kakul"],
                "description": "Which athlete — passed as the ? parameter in the query",
            },
            "sql": {
                "type": "string",
                "description": (
                    "SQL SELECT query. Always include WHERE user_id = ? "
                    "so results are scoped to this athlete."
                ),
            },
        },
        "required": ["user", "sql"],
    }

    def execute(self, **kwargs: Any) -> dict:
        user: str = kwargs["user"]
        sql: str = kwargs["sql"].strip()

        ok, reason = _is_read_only(sql)
        if not ok:
            return {"success": False, "error": reason}

        db_path = metrics_db_path(user)
        if not db_path.exists():
            return {"success": False, "error": "No metrics DB found. Run nightly sync first."}

        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            params = (user,) if "?" in sql else ()
            rows = conn.execute(sql, params).fetchall()
            conn.close()
            return {
                "success": True,
                "user": user,
                "row_count": len(rows),
                "rows": [dict(r) for r in rows],
            }
        except sqlite3.Error as e:
            return {"success": False, "error": f"SQL error: {e}"}
