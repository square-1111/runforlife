"""
Tests for the dynamic athlete roster (onboarding — de-hardcoding tezuesh/kakul).

The roster is the source of truth for "who is a configured athlete": directories
under RUNFORLIFE_HOME/athletes/<handle>/ that contain a profile.json. This
replaces the hardcoded config.USERS = ("tezuesh","kakul") tuple so a friend can
onboard under their own handle.

`valid_handle` is a pure syntactic check (used by auth, which runs BEFORE the
athlete dir exists during onboarding). `list_athletes` / `is_valid_athlete`
report who is actually configured on disk.

All storage is sandboxed to a tmp dir — never touches real ~/.runforlife.
"""

import pytest


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    from runforlife.storage import paths

    monkeypatch.setattr(paths, "RUNFORLIFE_HOME", tmp_path / ".runforlife")
    return tmp_path


def _make_athlete(sandbox, handle, with_profile=True):
    from runforlife.storage import paths

    d = paths.RUNFORLIFE_HOME / "athletes" / handle
    d.mkdir(parents=True, exist_ok=True)
    if with_profile:
        (d / "profile.json").write_text('{"name": "%s"}' % handle)
    return d


# --- valid_handle (pure syntax) ---------------------------------------------

@pytest.mark.parametrize("good", ["sam", "sam_r", "s1", "alex99", "a_b_c", "kakul"])
def test_valid_handle_accepts(good):
    from runforlife.storage.paths import valid_handle

    assert valid_handle(good) is True


@pytest.mark.parametrize("bad", ["Sam", "1sam", "sam-r", "sam r", "", "a", "_sam",
                                  "s" * 22, "SAM", "sam!", "a" * 21 + "b"])
def test_valid_handle_rejects(bad):
    from runforlife.storage.paths import valid_handle

    assert valid_handle(bad) is False


# --- list_athletes ----------------------------------------------------------

def test_list_athletes_empty_when_no_dir(sandbox):
    from runforlife.storage.paths import list_athletes

    assert list_athletes() == []


def test_list_athletes_returns_dirs_with_profile_sorted(sandbox):
    from runforlife.storage.paths import list_athletes

    _make_athlete(sandbox, "kakul")
    _make_athlete(sandbox, "alex")
    assert list_athletes() == ["alex", "kakul"]


def test_list_athletes_ignores_dirs_without_profile(sandbox):
    from runforlife.storage.paths import list_athletes

    _make_athlete(sandbox, "alex")
    _make_athlete(sandbox, "halfbaked", with_profile=False)
    assert list_athletes() == ["alex"]


# --- is_valid_athlete -------------------------------------------------------

def test_is_valid_athlete_true_for_configured(sandbox):
    from runforlife.storage.paths import is_valid_athlete

    _make_athlete(sandbox, "alex")
    assert is_valid_athlete("alex") is True


def test_is_valid_athlete_false_for_unconfigured(sandbox):
    from runforlife.storage.paths import is_valid_athlete

    _make_athlete(sandbox, "alex")
    assert is_valid_athlete("kakul") is False
    assert is_valid_athlete("nope") is False
