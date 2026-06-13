"""
Tests for the athlete-isolation PreToolUse guard.

Corrected threat model: block cross-athlete WRITES, allow cross-athlete READS
(reads enable /compare and inspection; writes were the 2026-06 data-loss vector).
The hook lives outside the package, so we load it by path. Pure over inputs.
"""

import importlib.util
from pathlib import Path

_HOOK_PATH = (
    Path(__file__).resolve().parents[1]
    / "runforlife-coach" / "hooks" / "pre_tool_use.py"
)


def _load_guard():
    spec = importlib.util.spec_from_file_location("pre_tool_use_guard", _HOOK_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load_guard()
KNOWN = ("tezuesh", "kakul")


def _bash(cmd, active):
    return guard._evaluate_bash(cmd, active, KNOWN)[0]


def _file(path, active):
    return guard._evaluate_file_tool(path, active, KNOWN)[0]


# --- /switch pointer write still allowed (the chicken-and-egg) ----------------

def test_switch_pointer_write_allowed_both_directions():
    assert _bash("printf 'tezuesh\\n' > ~/.runforlife/active_athlete", "kakul") is False
    assert _bash("printf 'kakul\\n' > ~/.runforlife/active_athlete", "tezuesh") is False


# --- NEW: cross-athlete READS are allowed (enables /compare) ------------------

def test_cross_athlete_sqlite_select_is_allowed():
    cmd = "sqlite3 ~/.runforlife/athletes/tezuesh/metrics.db 'SELECT date FROM daily_metrics'"
    assert _bash(cmd, "kakul") is False


def test_cross_athlete_cat_is_allowed():
    assert _bash("cat ~/.runforlife/athletes/tezuesh/profile.json", "kakul") is False


def test_select_with_created_at_column_not_flagged_as_write():
    # 'created_at' contains 'create' — must NOT be read as a CREATE write.
    cmd = "sqlite3 ~/.runforlife/athletes/tezuesh/metrics.db 'SELECT created_at FROM daily_metrics'"
    assert _bash(cmd, "kakul") is False


def test_compare_reading_both_athletes_allowed():
    cmd = ("sqlite3 ~/.runforlife/athletes/kakul/metrics.db 'SELECT 1'; "
           "sqlite3 ~/.runforlife/athletes/tezuesh/metrics.db 'SELECT 1'")
    assert _bash(cmd, "kakul") is False


# --- cross-athlete WRITES are blocked ----------------------------------------

def test_redirect_into_other_athlete_dir_blocked():
    assert _bash("echo x > ~/.runforlife/athletes/tezuesh/profile.json", "kakul") is True


def test_rm_other_athlete_dir_blocked():
    assert _bash("rm -rf ~/.runforlife/athletes/tezuesh", "kakul") is True


def test_sqlite_write_to_other_athlete_blocked():
    cmd = "sqlite3 ~/.runforlife/athletes/tezuesh/metrics.db 'DELETE FROM daily_metrics'"
    assert _bash(cmd, "kakul") is True


def test_user_flag_for_other_athlete_blocked():
    assert _bash("uv run python -m runforlife.sync.nightly --user tezuesh", "kakul") is True
    assert _bash("memory_manager.py --user=tezuesh --add-insight ...", "kakul") is True


def test_pointer_write_plus_foreign_user_write_is_blocked():
    # The bypass the audit found in the earlier fix: pointer touch + --user other.
    cmd = ("printf 'kakul\\n' > ~/.runforlife/active_athlete && "
           "uv run python -m runforlife.sync.nightly --user tezuesh")
    assert _bash(cmd, "kakul") is True


# --- same athlete / no athlete named -----------------------------------------

def test_same_athlete_write_allowed():
    assert _bash("sqlite3 ~/.runforlife/athletes/kakul/metrics.db 'DELETE FROM x'", "kakul") is False


def test_no_athlete_named_allowed():
    assert _bash("echo hello && ls /tmp", "kakul") is False


def test_no_active_athlete_blocks_write_allows_read():
    assert _bash("rm -rf ~/.runforlife/athletes/tezuesh", None) is True
    assert _bash("cat ~/.runforlife/athletes/tezuesh/profile.json", None) is False


# --- file tools (Edit/Write) — the previously-unguarded write vector ----------

def test_edit_other_athlete_file_blocked():
    assert _file("/Users/x/.runforlife/athletes/tezuesh/profile.json", "kakul") is True


def test_write_active_athlete_file_allowed():
    assert _file("/Users/x/.runforlife/athletes/kakul/ephemeral.json", "kakul") is False


def test_write_active_pointer_file_allowed():
    # The pointer file is NOT under athletes/<name>/ — never blocked.
    assert _file("/Users/x/.runforlife/active_athlete", "kakul") is False


def test_edit_non_athlete_file_allowed():
    assert _file("/Users/x/work/test/runforlife/src/runforlife/config.py", "kakul") is False
