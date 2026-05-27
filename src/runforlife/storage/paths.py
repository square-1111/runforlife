"""
Path resolution for per-user data directories.

All storage paths flow through here so there's one place to change
if the directory layout ever shifts.
"""

from pathlib import Path

from runforlife.config import DATA_DIR


def user_dir(user: str) -> Path:
    """Base directory for a user's data. Created on first access."""
    path = DATA_DIR / user
    path.mkdir(parents=True, exist_ok=True)
    return path


def conversation_db_path(user: str) -> Path:
    return user_dir(user) / "conversation.db"


def memory_db_path(user: str) -> Path:
    return user_dir(user) / "memory.db"


def profile_path(user: str) -> Path:
    return user_dir(user) / "profile.json"


def metrics_db_path(user: str) -> Path:
    return user_dir(user) / "metrics.db"


def personality_path(user: str) -> Path:
    return user_dir(user) / "personality.json"


def banister_path(user: str) -> Path:
    return user_dir(user) / "banister.json"
