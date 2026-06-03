#!/usr/bin/env python3
"""
PostToolUse hook for the RunForLife coach plugin (Phase 2).

This hook runs after a tool call completes (matcher "Bash" in hooks.json, but
written to tolerate any tool). Its job is cheap, best-effort housekeeping for
the self-improvement loop:

  1. Determine the active athlete (~/.runforlife/active_athlete). If none, do
     nothing and exit cleanly.
  2. Prune expired ephemeral context for that athlete. We prune here as well as
     in SessionStart/Stop because the Stop hook can be missed on crash/Ctrl-C,
     so eager pruning keeps stale context from leaking into later turns.
  3. Optionally append a lightweight, ts-less marker line to the athlete's
     .signal_buffer.jsonl noting which tool ran. This is a cheap breadcrumb the
     reflection/self-improvement loop can later use to notice activity. We only
     write it when it is clearly safe (athlete dir already exists, tool_name is
     a plausible short string) and skip silently on any doubt.

IMPORTANT: this hook reads ONLY tool_name / tool_input from stdin. It never
depends on any tool-result field (that field name is unreliable across Claude
Code versions). It must NEVER crash the session: every step is wrapped and the
process always exits 0 (a PostToolUse hook has no reason to block anything).
"""

import json
import sys
from pathlib import Path

# hooks/ -> runforlife-coach/ -> repo root -> src
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC_DIR = _REPO_ROOT / "src"

# Keep the breadcrumb file small and the tool_name sane. Magic limits as named
# constants so the intent is explicit.
_MAX_TOOL_NAME_LEN = 64
_MAX_BUFFER_BYTES = 256 * 1024  # 256 KiB — stop appending past this size
_SIGNAL_BUFFER_NAME = ".signal_buffer.jsonl"


def _ensure_src_on_path() -> None:
    """Make the runforlife package importable from the repo's src/ dir."""
    src = str(_SRC_DIR)
    if src not in sys.path:
        sys.path.insert(0, src)


def _read_stdin_json() -> dict:
    """Parse the hook's stdin JSON. Returns {} on any problem (never raises)."""
    try:
        raw = sys.stdin.read()
    except Exception:  # noqa: BLE001 - stdin may be closed/unreadable
        return {}
    if not raw or not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except Exception:  # noqa: BLE001 - malformed payload
        return {}
    return data if isinstance(data, dict) else {}


def _read_active_athlete() -> str | None:
    """Return the active athlete name, or None if unset/empty/missing."""
    from runforlife.storage.paths import active_athlete_file

    path = active_athlete_file()
    if not path.exists():
        return None
    name = path.read_text(encoding="utf-8").strip()
    return name or None


def _prune(athlete: str) -> None:
    """Best-effort prune of expired ephemeral context (never fatal)."""
    try:
        from runforlife.storage import athlete_memory

        athlete_memory.prune_ephemeral(athlete)
    except Exception:  # noqa: BLE001 - never crash the session
        pass


def _safe_tool_name(tool_name: object) -> str | None:
    """Return a short, sanitized tool name, or None if it's not usable."""
    if not isinstance(tool_name, str):
        return None
    name = tool_name.strip()
    if not name or len(name) > _MAX_TOOL_NAME_LEN:
        return None
    # Only keep simple identifier-ish names to avoid writing anything weird.
    if not all(ch.isalnum() or ch in ("_", "-", ".") for ch in name):
        return None
    return name


def _append_signal(athlete: str, tool_name: str) -> None:
    """Append a ts-less marker line to the athlete's signal buffer.

    Best-effort and conservative: only writes when the athlete dir already
    exists and the buffer hasn't grown unreasonably large. Any uncertainty
    means we skip silently — the breadcrumb is a nicety, not a requirement.
    """
    try:
        from runforlife.config import RUNFORLIFE_HOME  # type: ignore
    except Exception:  # noqa: BLE001 - config unavailable; skip the breadcrumb
        return

    try:
        athlete_dir = RUNFORLIFE_HOME / "athletes" / athlete
        # Only write if the athlete dir already exists; do NOT create it here.
        if not athlete_dir.is_dir():
            return

        buffer = athlete_dir / _SIGNAL_BUFFER_NAME
        if buffer.exists() and buffer.stat().st_size > _MAX_BUFFER_BYTES:
            return

        # ts-less marker: just the tool that ran, plus a stable event tag.
        line = json.dumps({"event": "post_tool_use", "tool_name": tool_name})
        with buffer.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception:  # noqa: BLE001 - breadcrumb is purely optional
        pass


def main() -> int:
    """Run the hook. Always returns 0 — PostToolUse never needs to block."""
    try:
        payload = _read_stdin_json()
        _ensure_src_on_path()

        athlete = _read_active_athlete()
        if athlete is None:
            return 0

        # Eager prune so stale ephemeral context is dropped between turns.
        _prune(athlete)

        # Optional, cheap breadcrumb for the self-improvement loop.
        tool_name = _safe_tool_name(payload.get("tool_name"))
        if tool_name is not None:
            _append_signal(athlete, tool_name)

        return 0
    except Exception:  # noqa: BLE001 - last-resort guard, never crash session
        return 0


if __name__ == "__main__":
    sys.exit(main())
