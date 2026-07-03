"""
Tests for the session_start hook's portability + onboarding-entry additions.

- _write_repo_path persists the repo root to ~/.runforlife/repo_path so slash
  commands can `cd "$(cat ~/.runforlife/repo_path)"` without a hardcoded path.
- _no_athlete_message points a brand-new install (empty roster) at /onboard, and
  an existing install (has athletes) at /switch with the real names.

The hook is a standalone plugin script (not in the package); it's loaded by path.
HOME is redirected to a tmp dir so nothing touches the real ~/.runforlife.
"""

import importlib.util
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / "runforlife-coach" / "hooks" / "session_start.py"


def _load():
    spec = importlib.util.spec_from_file_location("session_start_hook", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_write_repo_path_writes_real_repo_root(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    mod = _load()

    mod._write_repo_path()

    written = (tmp_path / ".runforlife" / "repo_path").read_text().strip()
    assert written == str(mod._REPO_ROOT)
    # It must point at a real checkout (src/runforlife exists under it).
    assert (Path(written) / "src" / "runforlife").is_dir()


def test_no_athlete_message_empty_roster_points_to_onboard():
    mod = _load()
    msg = mod._no_athlete_message([])
    assert "/onboard" in msg
    assert "/switch" not in msg


def test_no_athlete_message_existing_roster_points_to_switch():
    mod = _load()
    msg = mod._no_athlete_message(["alex", "sam"])
    assert "/switch" in msg
    assert "alex" in msg and "sam" in msg
    assert "/onboard" not in msg
