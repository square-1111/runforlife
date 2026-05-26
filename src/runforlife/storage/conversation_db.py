"""
Persistent conversation history using SQLite.

Stores the clean user/assistant text exchanges (not intermediate tool calls).
Each user has their own DB file in data/{user}/conversation.db.

Why we skip tool-call messages:
  Tool-use chains (user → tool → tool → assistant) are ephemeral reasoning steps.
  What matters across sessions is the human question and the final coach answer.
  Reinjecting tool-call chains into a new session would also confuse Claude.
"""

import sqlite3
from contextlib import contextmanager
from typing import Generator

from runforlife.storage.paths import conversation_db_path

_CREATE_TABLE = """\
CREATE TABLE IF NOT EXISTS messages (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    role      TEXT    NOT NULL CHECK (role IN ('user', 'assistant')),
    content   TEXT    NOT NULL,
    created_at TEXT   NOT NULL DEFAULT (datetime('now'))
)
"""


@contextmanager
def _conn(user: str) -> Generator[sqlite3.Connection, None, None]:
    db_path = conversation_db_path(user)
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


def save_message(user: str, role: str, content: str) -> None:
    """Persist a single message turn."""
    with _conn(user) as conn:
        conn.execute(
            "INSERT INTO messages (role, content) VALUES (?, ?)",
            (role, content),
        )
        conn.commit()


def load_recent(user: str, n: int = 40) -> list[dict]:
    """
    Load the last n messages as Anthropic-format dicts.

    Returns messages in chronological order (oldest first) so they
    slot directly into the Agent's conversation list.
    """
    with _conn(user) as conn:
        rows = conn.execute(
            "SELECT role, content FROM messages ORDER BY id DESC LIMIT ?",
            (n,),
        ).fetchall()

    # Reverse to get chronological order
    return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]
