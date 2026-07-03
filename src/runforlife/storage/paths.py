"""
Path resolution for per-athlete data directories.

All storage paths flow through here so there's one place to change
if the directory layout ever shifts.

Athlete data lives under RUNFORLIFE_HOME/athletes/<user>/ (outside the
repo, never committed). The legacy layout under DATA_DIR/<user> is still
exposed via legacy_user_dir() so the migration can read from it.
"""

import re
from pathlib import Path

from runforlife.config import DATA_DIR, RUNFORLIFE_HOME

# A handle becomes BOTH a directory name and an env-var stem
# (GARMIN_EMAIL_<HANDLE.upper()>), so it must be a valid, filesystem- and
# shell-safe identifier: lowercase, starts with a letter, 2-21 chars total.
_HANDLE_RE = re.compile(r"^[a-z][a-z0-9_]{1,20}$")


def valid_handle(name: str) -> bool:
    """Pure syntactic check for an athlete handle.

    Used by auth, which runs BEFORE the athlete dir exists during onboarding,
    so it validates shape only — not whether the athlete is configured on disk.
    """
    return bool(name) and bool(_HANDLE_RE.match(name))


def list_athletes() -> list[str]:
    """Configured athletes: sorted handles with a profile.json on disk.

    The dynamic source of truth that replaces the hardcoded config.USERS tuple.
    Reads RUNFORLIFE_HOME/athletes/*/profile.json without creating anything
    (unlike athlete_dir, which mkdirs on access).
    """
    root = RUNFORLIFE_HOME / "athletes"
    if not root.is_dir():
        return []
    return sorted(
        p.name for p in root.iterdir()
        if p.is_dir() and (p / "profile.json").is_file()
    )


def is_valid_athlete(name: str) -> bool:
    """True if `name` is a configured athlete (has a profile.json on disk)."""
    return name in list_athletes()


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
