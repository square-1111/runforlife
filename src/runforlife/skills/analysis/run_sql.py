"""
Dynamic SQL fallback — execute any SELECT against the daily_metrics table.

When fixed skills can't answer an analytical question, this skill lets
Claude write SQL directly. Covers one-off queries that don't justify a
dedicated skill: fastest day-of-week, longest streak ever, best 4-week
block, custom date range aggregations.

Safety: only SELECT statements are permitted.
"""

import sqlite3
from typing import Any

from runforlife.skills.base import Skill
from runforlife.storage.paths import metrics_db_path

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

        if not sql.upper().lstrip("( \n\t").startswith("SELECT"):
            return {"success": False, "error": "Only SELECT queries are permitted."}

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
