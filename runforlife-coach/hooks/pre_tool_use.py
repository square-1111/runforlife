#!/usr/bin/env python3
"""
PreToolUse hook for the RunForLife coach plugin (Phase 2) — athlete isolation guard.

Goal: a Bash command issued while athlete X is active must never read or write
athlete Y's data. A prior build agent destroyed real user data by mixing
athletes; this guard is the structural defense against a repeat.

Behavior (reads the PreToolUse JSON event from stdin):
  1. If tool_name != "Bash" -> exit 0 (only Bash commands can touch data dirs).
  2. Parse tool_input.command. Determine the active athlete from
     ~/.runforlife/active_athlete.
  3. Scan the command for references to a *known* athlete (by name token or by a
     path under ~/.runforlife/athletes/<name>) or to a --user <name> CLI arg.
  4. BLOCK (stderr reason + exit 2) when:
       - the command references a known athlete that differs from the active one
         (cross-athlete mismatch), OR
       - no active athlete is set AND the command clearly touches athlete data.
  5. Otherwise exit 0.

Design stance: CONSERVATIVE. When in doubt, ALLOW. Only a *clear* cross-athlete
mismatch (or athlete-data access with no active athlete) blocks. Any parse error
or unexpected failure -> exit 0 (fail open). A crashing hook must never break the
user's session, and an over-eager block is worse than a missed edge case here
because the SessionStart banner + explicit-arg discipline are the primary guard.
"""

import json
import re
import sys
from pathlib import Path

# hooks/ -> runforlife-coach/ -> repo root -> src
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC_DIR = _REPO_ROOT / "src"

# Known athlete names. Kept as a small literal set: the guard must work even if
# the runforlife package fails to import, and these two names are the entire
# multi-athlete universe for this single-machine deployment.
_KNOWN_ATHLETES = ("tezuesh", "kakul")

# Signals that a command "clearly touches athlete data" even without naming an
# athlete — used only when NO active athlete is set.
_DATA_CLI_MODULES = (
    "runforlife.rag.readiness",
    "runforlife.rag.banister",
    "runforlife.sync.nightly",
)


def _ensure_src_on_path() -> None:
    """Make the runforlife package importable from the repo's src/ dir."""
    src = str(_SRC_DIR)
    if src not in sys.path:
        sys.path.insert(0, src)


def _read_active_athlete() -> str | None:
    """Return the active athlete name, or None if unset/empty/missing.

    Tries the canonical paths helper first; falls back to a direct read of
    ~/.runforlife/active_athlete if the package can't be imported, so the guard
    keeps working even when the env is broken.
    """
    try:
        _ensure_src_on_path()
        from runforlife.storage.paths import active_athlete_file

        path = active_athlete_file()
    except Exception:  # noqa: BLE001 - fall back to a hard-coded path
        path = Path.home() / ".runforlife" / "active_athlete"

    try:
        if not path.exists():
            return None
        name = path.read_text(encoding="utf-8").strip()
        return name or None
    except Exception:  # noqa: BLE001 - unreadable pointer -> treat as unset
        return None


def _referenced_athletes(command: str) -> set[str]:
    """Return the set of KNOWN athlete names clearly referenced by the command.

    A name counts as referenced when it appears as:
      - a whole-word token (so "kakul" matches but "kakulish" / "akakul" do not),
        which covers `--user kakul`, `--user=kakul`, bare mentions, etc.; OR
      - a path segment under .runforlife/athletes/<name>/...

    Matching is case-insensitive and word-boundary aware to avoid false hits on
    substrings of unrelated words.
    """
    if not command:
        return set()

    referenced: set[str] = set()
    lowered = command.lower()

    for name in _KNOWN_ATHLETES:
        # Whole-word match: boundaries are anything that is not a word char.
        # This catches `--user kakul`, `--user=kakul`, `'kakul'`, `/kakul/`, etc.
        if re.search(rf"(?<![\w]){re.escape(name)}(?![\w])", lowered):
            referenced.add(name)

    return referenced


def _touches_athlete_data(command: str) -> bool:
    """Heuristic: does this command clearly access athlete data at all?

    Used only when no active athlete is set, to decide whether to nudge the user
    to /switch. Kept narrow on purpose — broad matching here would block benign
    commands when no athlete is loaded.
    """
    if not command:
        return False
    lowered = command.lower()

    if ".runforlife" in lowered:
        return True
    if "athletes/" in lowered or "athletes\\" in lowered:
        return True
    for module in _DATA_CLI_MODULES:
        if module in lowered and "--user" in lowered:
            return True
    return False


def _evaluate(command: str, active: str | None) -> tuple[bool, str]:
    """Decide whether to block. Returns (should_block, reason).

    reason is only meaningful when should_block is True.
    """
    referenced = _referenced_athletes(command)

    if active:
        # Block only on a genuine cross-athlete mismatch: the command names a
        # known athlete that is NOT the active one. Referencing the active
        # athlete (or no athlete) is fine.
        others = sorted(name for name in referenced if name != active)
        if others:
            other = others[0]
            reason = (
                f"[RunForLife] Blocked: command targets '{other}' but the active "
                f"athlete is '{active}'. This guard prevents mixing "
                f"{other}'s and {active}'s data.\n"
                f"Run /switch {other} first if you really mean to act on {other}."
            )
            return True, reason
        return False, ""

    # No active athlete set. Block only if the command clearly touches athlete
    # data (named athlete, .runforlife path, or a data CLI with --user).
    if referenced or _touches_athlete_data(command):
        reason = (
            "[RunForLife] Blocked: no active athlete is set, but this command "
            "touches athlete data. Run /switch <tezuesh|kakul> to load an "
            "athlete before running data, readiness, banister, or sync commands."
        )
        return True, reason

    return False, ""


def main() -> int:
    """Run the guard. Exit 2 to block; exit 0 to allow (incl. all errors)."""
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return 0
        event = json.loads(raw)
        if not isinstance(event, dict):
            return 0

        if event.get("tool_name") != "Bash":
            return 0

        tool_input = event.get("tool_input")
        if not isinstance(tool_input, dict):
            return 0
        command = tool_input.get("command")
        if not isinstance(command, str) or not command.strip():
            return 0

        active = _read_active_athlete()
        should_block, reason = _evaluate(command, active)
        if should_block:
            print(reason, file=sys.stderr)
            return 2
        return 0
    except Exception:  # noqa: BLE001 - fail open; never break the session
        return 0


if __name__ == "__main__":
    sys.exit(main())
