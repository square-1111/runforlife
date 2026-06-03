"""
Four-file JSON memory API for an athlete.

The coach's durable memory is split across four files in the athlete dir:

  profile.json    — static facts (read-only here; seeded by athlete_init)
  insights.json   — learned, long-lived insights about the athlete
  ephemeral.json  — short-lived context items with an optional expiry date
  feedback.json   — record of advice given and how the athlete reacted

All writes are atomic: a temp file is written in the same directory and then
os.replace'd over the target, so a crash mid-write never corrupts the file.
List files auto-create with their empty envelope on first read, and ids
auto-increment (max existing id + 1).
"""

import json
import os
import tempfile
from datetime import date
from pathlib import Path

from runforlife.storage.paths import (
    ephemeral_path,
    feedback_path,
    insights_path,
    profile_path,
)


def _atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON atomically: temp file in the same dir + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        # Clean up the temp file on any failure; never leave a stray .tmp.
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise


def _load_envelope(path: Path, key: str) -> dict:
    """Load a {key: [...]} envelope, creating an empty one if missing."""
    if not path.exists():
        empty = {key: []}
        _atomic_write_json(path, empty)
        return empty
    data = json.loads(path.read_text(encoding="utf-8"))
    if key not in data or not isinstance(data[key], list):
        data[key] = []
    return data


def _next_id(items: list[dict]) -> int:
    """Auto-incrementing id = max existing id + 1 (1-based)."""
    return max((int(item.get("id", 0)) for item in items), default=0) + 1


# ---------------------------------------------------------------------------
# profile (read-only)
# ---------------------------------------------------------------------------

def load_profile(user: str) -> dict:
    """Load the athlete profile. The coach reads this, never writes it."""
    path = profile_path(user)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# insights
# ---------------------------------------------------------------------------

def load_insights(user: str) -> list[dict]:
    """Return all stored insights."""
    return _load_envelope(insights_path(user), "insights")["insights"]


def add_insight(user: str, insight: str, type: str, confidence: float = 0.5) -> int:
    """Append a new insight. Returns the new insight's id."""
    path = insights_path(user)
    data = _load_envelope(path, "insights")
    items = data["insights"]
    new_id = _next_id(items)
    today = date.today().isoformat()
    items.append({
        "id": new_id,
        "insight": insight,
        "type": type,
        "confidence": confidence,
        "discovered": today,
        "last_reinforced": today,
    })
    _atomic_write_json(path, data)
    return new_id


# ---------------------------------------------------------------------------
# ephemeral
# ---------------------------------------------------------------------------

def load_active_ephemeral(user: str) -> list[dict]:
    """Return only non-expired ephemeral items (expires_on null or >= today)."""
    today = date.today().isoformat()
    items = _load_envelope(ephemeral_path(user), "items")["items"]
    return [
        item for item in items
        if item.get("expires_on") is None or item["expires_on"] >= today
    ]


def add_ephemeral(user: str, content: str, expires_on: str | None) -> int:
    """Append a new ephemeral item. Returns the new item's id."""
    path = ephemeral_path(user)
    data = _load_envelope(path, "items")
    items = data["items"]
    new_id = _next_id(items)
    items.append({
        "id": new_id,
        "content": content,
        "expires_on": expires_on,
        "created_at": date.today().isoformat(),
    })
    _atomic_write_json(path, data)
    return new_id


def prune_ephemeral(user: str) -> int:
    """Delete expired ephemeral items. Returns the count removed."""
    today = date.today().isoformat()
    path = ephemeral_path(user)
    data = _load_envelope(path, "items")
    items = data["items"]
    kept = [
        item for item in items
        if item.get("expires_on") is None or item["expires_on"] >= today
    ]
    removed = len(items) - len(kept)
    if removed:
        data["items"] = kept
        _atomic_write_json(path, data)
    return removed


# ---------------------------------------------------------------------------
# feedback
# ---------------------------------------------------------------------------

def load_feedback(user: str) -> list[dict]:
    """Return all feedback records."""
    return _load_envelope(feedback_path(user), "items")["items"]


def add_feedback(
    user: str,
    advice_type: str,
    advice: str,
    rating: str,
    adherence: str | None = None,
    outcome: str | None = None,
) -> int:
    """Append a new feedback record. Returns the new record's id."""
    path = feedback_path(user)
    data = _load_envelope(path, "items")
    items = data["items"]
    new_id = _next_id(items)
    items.append({
        "id": new_id,
        "date": date.today().isoformat(),
        "advice_type": advice_type,
        "advice": advice,
        "rating": rating,
        "adherence": adherence,
        "outcome": outcome,
    })
    _atomic_write_json(path, data)
    return new_id
