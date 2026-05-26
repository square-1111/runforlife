"""
Current run streak and rest day analysis.

People ask this constantly: "how many days in a row have I run?",
"when did I last take a rest day?", "what's my longest streak?".
Gap detection in SQL is messy — cleaner as Python over recent rows.
"""

from datetime import date, timedelta
from typing import Any

from runforlife.skills.base import Skill
from runforlife.storage.metrics_store import get_window


class RunStreak(Skill):
    name = "run_streak"

    description = (
        "Get the current run streak (consecutive days with a run), last rest day, "
        "and longest streak in the last 90 days. "
        "Use when the athlete asks 'how many days in a row have I run?', "
        "'when did I last rest?', 'what's my streak?', 'am I due a rest day?'."
    )

    input_schema = {
        "type": "object",
        "properties": {
            "user": {
                "type": "string",
                "enum": ["tezuesh", "kakul"],
                "description": "Which athlete",
            },
        },
        "required": ["user"],
    }

    def execute(self, **kwargs: Any) -> dict:
        user: str = kwargs["user"]

        today = date.today()
        rows = get_window(user, today.isoformat(), 90)

        if not rows:
            return {
                "success": True,
                "user": user,
                "current_streak": 0,
                "last_rest_day": None,
                "longest_streak_90d": 0,
                "note": "No data. Run nightly sync first.",
            }

        # Build a date → ran_today lookup
        by_date: dict[str, bool] = {r["date"]: bool(r.get("ran_today")) for r in rows}

        # Current streak: walk backwards from today
        current_streak = 0
        d = today
        while True:
            s = d.isoformat()
            if s not in by_date:
                break
            if not by_date[s]:
                break
            current_streak += 1
            d -= timedelta(days=1)

        # Last rest day
        last_rest_day = None
        d = today
        for _ in range(90):
            s = d.isoformat()
            if s in by_date and not by_date[s]:
                last_rest_day = s
                break
            d -= timedelta(days=1)

        # Longest streak in the window
        longest = 0
        current = 0
        for row in rows:  # oldest first
            if row.get("ran_today"):
                current += 1
                longest = max(longest, current)
            else:
                current = 0

        return {
            "success": True,
            "user": user,
            "current_streak": current_streak,
            "last_rest_day": last_rest_day,
            "longest_streak_90d": longest,
            "days_run_last_7": sum(1 for r in rows[-7:] if r.get("ran_today")),
            "days_run_last_30": sum(1 for r in rows[-30:] if r.get("ran_today")),
        }
