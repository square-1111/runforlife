#!/usr/bin/env python3
"""
PreToolUse hook for the RunForLife coach plugin — athlete isolation guard.

Threat model (corrected): the operation that destroyed real data in 2026-06 was
a cross-athlete *write* — touching athlete Y's files while athlete X is active.
So this guard blocks cross-athlete WRITES and allows cross-athlete READS.

Why allow reads? Reading another athlete's data (a SELECT, a `cat`, the plugin's
own docs that merely mention a name) is harmless and is exactly what a two-person
household needs — e.g. /compare reads both athletes. The earlier guard blocked
all references (reads included), which walled off legitimate comparison while
STILL leaving the real write path open via the Edit/Write tools and a
pointer-write bypass. This version fixes both.

What blocks (when an active athlete is set and the op targets a DIFFERENT, known
athlete):
  Bash:
    - a redirect (> / >>) into  ~/.runforlife/athletes/<other>/...
    - a mutating coreutil (rm, mv, cp, tee, truncate, dd, ln, ...) targeting that dir
    - a sqlite3 write (INSERT/UPDATE/DELETE/DROP/ALTER) against that dir
    - a data CLI invoked with --user <other> / --user=<other>
  Edit / Write / NotebookEdit / MultiEdit:
    - file_path under ~/.runforlife/athletes/<other>/...   (the original write vector)

What is allowed: read-only cross-athlete access (SELECT/cat/read), bare mentions,
the /switch pointer write (~/.runforlife/active_athlete — not under athletes/),
and anything touching only the active athlete.

Roster is discovered dynamically from disk (∪ the active athlete) so a newly
added athlete is guarded too, not silently unprotected — and no author handles
are baked in, so the guard is correct on a friend's install.

Fail-open is deliberate: an unexpected hook crash returns exit 0 rather than
bricking the user's session. The structured checks below are the protection; a
belt-and-suspenders SessionStart banner and explicit-arg discipline back them up.
"""

import json
import re
import sys
from pathlib import Path

# hooks/ -> runforlife-coach/ -> repo root -> src
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC_DIR = _REPO_ROOT / "src"

# Mutating shell commands that, when targeting another athlete's dir, are writes.
_MUTATING_CMDS = (
    "rm", "rmdir", "mv", "cp", "tee", "truncate", "dd", "ln",
    "install", "shred", "rsync", "chmod", "chown",
)
# SQL keywords that mean a write. Word-boundary matched so "created_at" (a column)
# and the replace() function don't trip a read; the common write verbs suffice.
_SQL_WRITE_KEYWORDS = ("insert", "update", "delete", "drop", "alter")

# Tools that write files (vs read-only Read). file_path under another athlete's
# dir is the exact 2026-06 write vector and was previously unguarded.
_FILE_TOOLS = ("Edit", "Write", "NotebookEdit", "MultiEdit")


def _ensure_src_on_path() -> None:
    src = str(_SRC_DIR)
    if src not in sys.path:
        sys.path.insert(0, src)


def _known_athletes() -> tuple[str, ...]:
    """Roster = on-disk athlete dirs ∪ the active athlete.

    Discovered dynamically from disk (no hardcoded names) so the guard is correct
    on any machine — a friend's install has its own handles, not tezuesh/kakul.
    """
    names: set[str] = set()
    try:
        athletes_dir = Path.home() / ".runforlife" / "athletes"
        if athletes_dir.is_dir():
            names.update(p.name for p in athletes_dir.iterdir() if p.is_dir())
    except Exception:  # noqa: BLE001
        pass
    active = _read_active_athlete()
    if active:
        names.add(active)
    return tuple(sorted(names))


def _read_active_athlete() -> str | None:
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


def _cli_user_targets(command: str, known: tuple[str, ...]) -> set[str]:
    """Athletes named via `--user <name>` / `--user=<name>` — a CLI data op.

    A CLI told to operate on another athlete is a cross-athlete operation
    regardless of whether that particular subcommand reads or writes; treated
    conservatively as blocking, because read-only comparison goes through direct
    SELECTs (allowed below), not through --user.
    """
    found: set[str] = set()
    lowered = command.lower()
    for name in known:
        if re.search(rf"--user(?:\s+|=)['\"]?{re.escape(name.lower())}(?![\w])", lowered):
            found.add(name)
    return found


def _path_write_targets(command: str, known: tuple[str, ...]) -> set[str]:
    """Athletes whose athletes/<name>/ dir the command WRITES to.

    Read-only access (sqlite SELECT, cat, a python read) is intentionally NOT a
    write and is allowed — that's what enables /compare and inspection. Only a
    redirect into the dir, a mutating coreutil targeting it, or a sqlite write
    against it counts.
    """
    lowered = command.lower()
    has_sqlite = "sqlite3" in lowered
    has_sql_write = has_sqlite and bool(
        re.search(rf"\b(?:{'|'.join(_SQL_WRITE_KEYWORDS)})\b", lowered)
    )
    cmds = "|".join(_MUTATING_CMDS)
    found: set[str] = set()
    for name in known:
        nm = re.escape(name.lower())
        if not re.search(rf"athletes[/\\]{nm}(?![\w])", lowered):
            continue
        if re.search(rf">>?\s*\S*athletes[/\\]{nm}", lowered):
            found.add(name)
        elif re.search(rf"\b(?:{cmds})\b[^|&;\n]*athletes[/\\]{nm}", lowered):
            found.add(name)
        elif has_sql_write:
            found.add(name)
    return found


def _evaluate_bash(command: str, active: str | None, known: tuple[str, ...]) -> tuple[bool, str]:
    cli = _cli_user_targets(command, known)
    writes = _path_write_targets(command, known)

    if active:
        offenders = sorted((cli | writes) - {active})
        if offenders:
            other = offenders[0]
            how = "writes to" if other in writes else "runs a data CLI (--user) for"
            reason = (
                f"[RunForLife] Blocked: command {how} '{other}' but the active "
                f"athlete is '{active}'. This guard prevents a cross-athlete WRITE "
                f"corrupting {other}'s data.\n"
                f"Reads are fine; run /switch {other} first to act on {other}."
            )
            return True, reason
        return False, ""

    # No active athlete: cross-athlete READS are harmless; only block WRITES.
    offenders = sorted(cli | writes)
    if offenders:
        reason = (
            "[RunForLife] Blocked: no active athlete is set and this command would "
            "WRITE athlete data. Run /switch <athlete> first."
        )
        return True, reason
    return False, ""


_ATHLETE_PATH_RE = re.compile(r"\.runforlife/athletes/([^/\\]+)[/\\]", re.IGNORECASE)


def _evaluate_file_tool(file_path: str | None, active: str | None,
                        known: tuple[str, ...]) -> tuple[bool, str]:
    """Block an Edit/Write whose target is under another athlete's data dir."""
    if not file_path:
        return False, ""
    norm = str(file_path).replace("\\", "/")
    m = _ATHLETE_PATH_RE.search(norm)
    if not m:
        return False, ""
    target = m.group(1).lower()
    known_lower = {k.lower() for k in known}
    if target not in known_lower:
        return False, ""
    if not active or target == active.lower():
        return False, ""
    reason = (
        f"[RunForLife] Blocked: this edit/write targets '{target}'s data file but "
        f"the active athlete is '{active}'. Cross-athlete file writes are the exact "
        f"path that caused prior data loss.\nRun /switch {target} first."
    )
    return True, reason


def main() -> int:
    """Run the guard. Exit 2 to block; exit 0 to allow (incl. all errors)."""
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return 0
        event = json.loads(raw)
        if not isinstance(event, dict):
            return 0

        tool_name = event.get("tool_name")
        tool_input = event.get("tool_input")
        if not isinstance(tool_input, dict):
            return 0

        active = _read_active_athlete()
        known = _known_athletes()

        if tool_name == "Bash":
            command = tool_input.get("command")
            if not isinstance(command, str) or not command.strip():
                return 0
            should_block, reason = _evaluate_bash(command, active, known)
        elif tool_name in _FILE_TOOLS:
            file_path = tool_input.get("file_path") or tool_input.get("notebook_path")
            should_block, reason = _evaluate_file_tool(file_path, active, known)
        else:
            return 0

        if should_block:
            print(reason, file=sys.stderr)
            return 2
        return 0
    except Exception:  # noqa: BLE001 - fail open; never break the session
        return 0


if __name__ == "__main__":
    sys.exit(main())
