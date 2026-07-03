"""
Tests that the CLI entry points no longer hardcode tezuesh/kakul.

- auth accepts any syntactically-valid handle (it runs BEFORE the athlete dir
  exists during onboarding) and rejects malformed ones.
- nightly's --user resolves `all` to the dynamic roster, not a fixed tuple.

Sandboxed; no network (authenticate / sync are monkeypatched out).
"""

import sys

import pytest


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    from runforlife.storage import paths

    monkeypatch.setattr(paths, "RUNFORLIFE_HOME", tmp_path / ".runforlife")
    return tmp_path


def _make_athlete(sandbox, handle):
    from runforlife.storage import paths

    d = paths.RUNFORLIFE_HOME / "athletes" / handle
    d.mkdir(parents=True, exist_ok=True)
    (d / "profile.json").write_text('{"name": "%s"}' % handle)


# --- auth.main handle gate --------------------------------------------------

def test_auth_main_accepts_brand_new_valid_handle(monkeypatch):
    from runforlife import auth

    called = []
    monkeypatch.setattr(auth, "authenticate", lambda u: called.append(u))
    monkeypatch.setattr(sys, "argv", ["auth", "newfriend"])
    auth.main()
    assert called == ["newfriend"]


def test_auth_main_rejects_malformed_handle(monkeypatch):
    from runforlife import auth

    called = []
    monkeypatch.setattr(auth, "authenticate", lambda u: called.append(u))
    monkeypatch.setattr(sys, "argv", ["auth", "Bad-Handle"])
    with pytest.raises(SystemExit):
        auth.main()
    assert called == []


# --- nightly --user resolution ----------------------------------------------

def test_nightly_resolve_all_uses_roster(sandbox):
    from runforlife.sync import nightly

    _make_athlete(sandbox, "alex")
    _make_athlete(sandbox, "sam")
    assert nightly._resolve_users("all") == ["alex", "sam"]


def test_nightly_resolve_single_handle(sandbox):
    from runforlife.sync import nightly

    _make_athlete(sandbox, "alex")
    assert nightly._resolve_users("alex") == ["alex"]
