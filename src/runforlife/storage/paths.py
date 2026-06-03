"""
Path resolution for per-athlete data directories.

All storage paths flow through here so there's one place to change
if the directory layout ever shifts.

Athlete data lives under RUNFORLIFE_HOME/athletes/<user>/ (outside the
repo, never committed). The legacy layout under DATA_DIR/<user> is still
exposed via legacy_user_dir() so the migration can read from it.
"""

from pathlib import Path

from runforlife.config import DATA_DIR, RUNFORLIFE_HOME


def athlete_dir(user: str) -> Path:
    """Base directory for an athlete's data. Created on first access."""
    path = RUNFORLIFE_HOME / "athletes" / user
    path.mkdir(parents=True, exist_ok=True)
    return path


def profile_path(user: str) -> Path:
    return athlete_dir(user) / "profile.json"


def insights_path(user: str) -> Path:
    return athlete_dir(user) / "insights.json"


def ephemeral_path(user: str) -> Path:
    return athlete_dir(user) / "ephemeral.json"


def feedback_path(user: str) -> Path:
    return athlete_dir(user) / "feedback.json"


def personality_path(user: str) -> Path:
    return athlete_dir(user) / "personality.json"


def metrics_db_path(user: str) -> Path:
    return athlete_dir(user) / "metrics.db"


def banister_path(user: str) -> Path:
    return athlete_dir(user) / "banister.json"


def conversation_db_path(user: str) -> Path:
    return athlete_dir(user) / "conversation.db"


def memory_db_path(user: str) -> Path:
    """Legacy memory.db location under the new athlete dir (migration use)."""
    return athlete_dir(user) / "memory.db"


def tokens_dir(user: str) -> Path:
    """garth tokens dir for an athlete, created with mode 0700."""
    path = athlete_dir(user) / "tokens"
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def active_athlete_file() -> Path:
    """Plain-text file holding the active athlete name (single line)."""
    return RUNFORLIFE_HOME / "active_athlete"


def legacy_user_dir(user: str) -> Path:
    """OLD data location (DATA_DIR/<user>) — the migration source. Not created."""
    return DATA_DIR / user
