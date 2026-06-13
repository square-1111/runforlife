"""
Tests for the canonical atomic_write_json in runforlife.storage.athlete_memory.

This is the single fsync-correct JSON writer that the coach scripts
(memory_manager / athlete_init / migrate_data) now share instead of keeping
their own copies. The test asserts a clean round-trip and that no stray .tmp
file is left behind.

Sandboxed: writes only under a tmp dir, never the real ~/.runforlife.
"""

import json


def test_atomic_write_json_round_trips(tmp_path):
    from runforlife.storage.athlete_memory import atomic_write_json

    target = tmp_path / "nested" / "data.json"
    payload = {"items": [{"id": 1, "content": "hello"}], "n": 2}

    atomic_write_json(target, payload)

    assert target.exists()
    assert json.loads(target.read_text(encoding="utf-8")) == payload
    # No leftover temp files in the target directory.
    assert list(target.parent.glob("*.tmp")) == []


def test_atomic_write_json_overwrites_existing(tmp_path):
    from runforlife.storage.athlete_memory import atomic_write_json

    target = tmp_path / "data.json"
    atomic_write_json(target, {"v": 1})
    atomic_write_json(target, {"v": 2})

    assert json.loads(target.read_text(encoding="utf-8")) == {"v": 2}
