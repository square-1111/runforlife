"""
Tests for the upgraded athlete_init scaffolder (onboarding).

The scaffolder now:
  - writes a full/valid profile.json (a passed-in dict verbatim, or a sensible
    default from name/gender/units), not the old skeleton;
  - seeds empty insights/ephemeral/feedback;
  - does NOT create the dead ~/.runforlife/athletes/<h>/tokens dir (auth writes
    tokens to repo/tokens, so that dir was never read);
  - is idempotent (existing files are not clobbered).

Loaded by path (it's a plugin script, not a package module). Sandboxed to tmp.
"""

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "runforlife-coach" / "scripts" / "athlete_init.py"


def _load():
    spec = importlib.util.spec_from_file_location("athlete_init_script", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    from runforlife.storage import paths

    monkeypatch.setattr(paths, "RUNFORLIFE_HOME", tmp_path / ".runforlife")
    return tmp_path


def _read_profile(sandbox, handle):
    p = sandbox / ".runforlife" / "athletes" / handle / "profile.json"
    return json.loads(p.read_text())


def test_build_default_profile_shape():
    mod = _load()
    prof = mod.build_default_profile("sam", name="Sam R", gender="male", units="imperial")
    assert prof["name"] == "Sam R"
    assert prof["garmin_user"] == "sam"
    assert prof["gender"] == "male"
    assert prof["prefs"]["units"] == "imperial"
    assert isinstance(prof["goals"], dict)
    assert "watch" in prof["context"]


def test_init_writes_default_profile_and_seeds(sandbox):
    mod = _load()
    mod.init_athlete("sam", name="Sam R")

    prof = _read_profile(sandbox, "sam")
    assert prof["garmin_user"] == "sam"
    base = sandbox / ".runforlife" / "athletes" / "sam"
    for f in ("insights.json", "ephemeral.json", "feedback.json"):
        assert (base / f).is_file()


def test_init_writes_given_profile_verbatim(sandbox):
    mod = _load()
    full = {"name": "Sam", "garmin_user": "sam", "goals": {"half_marathon": {"target_time": "1:45:00"}}}
    mod.init_athlete("sam", profile=full)

    prof = _read_profile(sandbox, "sam")
    assert prof["goals"]["half_marathon"]["target_time"] == "1:45:00"


def test_init_does_not_create_dead_tokens_dir(sandbox):
    mod = _load()
    mod.init_athlete("sam")
    assert not (sandbox / ".runforlife" / "athletes" / "sam" / "tokens").exists()


def test_init_is_idempotent(sandbox):
    mod = _load()
    mod.init_athlete("sam", profile={"name": "Original", "garmin_user": "sam"})
    mod.init_athlete("sam", profile={"name": "Changed", "garmin_user": "sam"})
    assert _read_profile(sandbox, "sam")["name"] == "Original"
