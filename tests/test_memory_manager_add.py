"""
Tests for the memory_manager.py --add-insight / --add-ephemeral CLI actions.

Exercises the command functions that wrap athlete_memory.add_insight and
add_ephemeral, and asserts the records persist where the coach reads them
(load_insights / load_active_ephemeral).

Fully sandboxed: RUNFORLIFE_HOME is redirected to a tmp dir, so no real athlete
data is read or written.
"""

import importlib.util
from datetime import date, timedelta
from pathlib import Path

import pytest


@pytest.fixture()
def sandbox_home(tmp_path, monkeypatch):
    """Point all athlete storage at a throwaway tmp dir."""
    from runforlife.storage import paths

    fake_home = tmp_path / ".runforlife"
    monkeypatch.setattr(paths, "RUNFORLIFE_HOME", fake_home)
    return fake_home


@pytest.fixture()
def memory_manager():
    """Import the memory_manager script by path (it lives outside the package)."""
    script_path = (
        Path(__file__).resolve().parents[1]
        / "runforlife-coach" / "scripts" / "memory_manager.py"
    )
    spec = importlib.util.spec_from_file_location("memory_manager", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_add_insight_persists_record(sandbox_home, memory_manager, capsys):
    from runforlife.storage import athlete_memory

    memory_manager._cmd_add_insight(
        "tezuesh",
        insight="Responds well to back-to-back easy days after races",
        insight_type="recovery",
        confidence=0.7,
    )

    insights = athlete_memory.load_insights("tezuesh")
    assert len(insights) == 1
    record = insights[0]
    assert record["id"] == 1
    assert record["insight"] == "Responds well to back-to-back easy days after races"
    assert record["type"] == "recovery"
    assert record["confidence"] == 0.7

    out = capsys.readouterr().out
    assert "insight id 1" in out


def test_add_ephemeral_persists_active_item(sandbox_home, memory_manager, capsys):
    from runforlife.storage import athlete_memory

    future = (date.today() + timedelta(days=7)).isoformat()
    memory_manager._cmd_add_ephemeral(
        "kakul",
        content="Travelling Mon-Fri, treadmill only",
        expires_on=future,
    )

    active = athlete_memory.load_active_ephemeral("kakul")
    assert len(active) == 1
    record = active[0]
    assert record["id"] == 1
    assert record["content"] == "Travelling Mon-Fri, treadmill only"
    assert record["expires_on"] == future

    out = capsys.readouterr().out
    assert "ephemeral id 1" in out


def test_add_ephemeral_without_expiry_is_active(sandbox_home, memory_manager):
    from runforlife.storage import athlete_memory

    memory_manager._cmd_add_ephemeral(
        "tezuesh",
        content="Switched to a new pre-workout supplement",
        expires_on=None,
    )

    active = athlete_memory.load_active_ephemeral("tezuesh")
    assert len(active) == 1
    assert active[0]["expires_on"] is None


def test_expired_ephemeral_is_not_active(sandbox_home, memory_manager):
    """An item whose expiry is in the past must not surface as active context."""
    from runforlife.storage import athlete_memory

    past = (date.today() - timedelta(days=1)).isoformat()
    memory_manager._cmd_add_ephemeral("kakul", content="old travel note", expires_on=past)

    assert athlete_memory.load_active_ephemeral("kakul") == []
