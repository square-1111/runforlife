"""
Durable memory store for facts learned during conversation.

Memories are short text facts that persist across sessions and get
auto-injected into the system prompt so the coach always has context.

Examples:
  - "Travelling to Singapore May 28–June 3"
  - "Left knee feeling tight this week"
  - "Targeting 4:05/km pace for next long run"

Each memory has an optional expiry date. The nightly sync prunes expired ones.
"""

import sqlite3
from contextlib import contextmanager
from datetime import date
from typing import Generator

from runforlife.storage.paths import memory_db_path

_CREATE_TABLE = """\
CREATE TABLE IF NOT EXISTS memories (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    content    TEXT    NOT NULL,
    expires_on TEXT,
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
)
"""


@contextmanager
def _conn(user: str) -> Generator[sqlite3.Connection, None, None]:
    db_path = memory_db_path(user)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    try:
        conn.execute(_CREATE_TABLE)
        conn.commit()
        yield conn
    finally:
        conn.close()


def save_memory(user: str, content: str, expires_on: str | None = None) -> int:
    """Store a new memory. Returns the new memory's ID."""
    with _conn(user) as conn:
        cursor = conn.execute(
            "INSERT INTO memories (content, expires_on) VALUES (?, ?)",
            (content, expires_on),
        )
        conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]


def load_active_memories(user: str) -> list[str]:
    """Return all non-expired memory strings, newest first."""
    today = date.today().isoformat()
    with _conn(user) as conn:
        rows = conn.execute(
            """
            SELECT content FROM memories
            WHERE expires_on IS NULL OR expires_on >= ?
            ORDER BY id DESC
            """,
            (today,),
        ).fetchall()
    return [row["content"] for row in rows]


def delete_memory(user: str, memory_id: int) -> bool:
    """Delete a memory by ID. Returns True if it existed."""
    with _conn(user) as conn:
        cursor = conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        conn.commit()
        return cursor.rowcount > 0


def list_memories(user: str) -> list[dict]:
    """Return all memories with IDs for management."""
    today = date.today().isoformat()
    with _conn(user) as conn:
        rows = conn.execute(
            """
            SELECT id, content, expires_on, created_at,
                   CASE WHEN expires_on IS NOT NULL AND expires_on < ? THEN 1 ELSE 0 END as expired
            FROM memories
            ORDER BY id DESC
            """,
            (today,),
        ).fetchall()
    return [dict(row) for row in rows]


def prune_expired(user: str) -> int:
    """Delete expired memories. Returns count deleted."""
    today = date.today().isoformat()
    with _conn(user) as conn:
        cursor = conn.execute(
            "DELETE FROM memories WHERE expires_on IS NOT NULL AND expires_on < ?",
            (today,),
        )
        conn.commit()
        return cursor.rowcount
