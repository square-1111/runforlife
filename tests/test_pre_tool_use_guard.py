"""
Tests for the athlete-isolation PreToolUse guard, focused on the /switch
chicken-and-egg fix: the guard must allow a command that writes the
active_athlete pointer even though it names the incoming (non-active) athlete,
while still blocking any command that reaches into another athlete's data dir.

The hook lives outside the package (runforlife-coach/hooks/), so we load it by
path. No real athlete data is touched — _evaluate is pure over (command, active).
"""

import importlib.util
from pathlib import Path

import pytest

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


# --- the bug this fixes: /switch's own pointer write must be allowed ----------

def test_switch_pointer_write_to_other_athlete_is_allowed():
    # Active is kakul; /switch tezuesh writes the pointer naming tezuesh.
    cmd = "mkdir -p ~/.runforlife && printf '%s\\n' \"tezuesh\" > ~/.runforlife/active_athlete"
    should_block, _ = guard._evaluate(cmd, active="kakul")
    assert should_block is False


def test_switch_pointer_write_reverse_direction_allowed():
    cmd = "printf 'kakul\\n' > ~/.runforlife/active_athlete"
    should_block, _ = guard._evaluate(cmd, active="tezuesh")
    assert should_block is False


# --- the protection must still hold: reaching into another athlete's data -----

def test_cross_athlete_data_dir_access_still_blocked():
    cmd = "sqlite3 ~/.runforlife/athletes/tezuesh/metrics.db 'SELECT 1'"
    should_block, reason = guard._evaluate(cmd, active="kakul")
    assert should_block is True
    assert "tezuesh" in reason


def test_pointer_write_that_also_touches_other_data_dir_is_blocked():
    # A pointer write is NOT a free pass to also read the other athlete's dir.
    cmd = (
        "printf 'kakul\\n' > ~/.runforlife/active_athlete && "
        "cat ~/.runforlife/athletes/tezuesh/profile.json"
    )
    should_block, reason = guard._evaluate(cmd, active="kakul")
    assert should_block is True
    assert "tezuesh" in reason


def test_bare_user_flag_for_other_athlete_still_blocked():
    cmd = "uv run python -m runforlife.sync.nightly --user tezuesh"
    should_block, _ = guard._evaluate(cmd, active="kakul")
    assert should_block is True


# --- unchanged baseline behavior ---------------------------------------------

def test_same_athlete_access_allowed():
    cmd = "sqlite3 ~/.runforlife/athletes/kakul/metrics.db 'SELECT 1'"
    should_block, _ = guard._evaluate(cmd, active="kakul")
    assert should_block is False


def test_reading_pointer_is_allowed():
    cmd = "cat ~/.runforlife/active_athlete"
    should_block, _ = guard._evaluate(cmd, active="kakul")
    assert should_block is False


@pytest.mark.parametrize("active", ["tezuesh", "kakul"])
def test_no_athlete_named_is_allowed(active):
    cmd = "echo hello && ls /tmp"
    should_block, _ = guard._evaluate(cmd, active=active)
    assert should_block is False
