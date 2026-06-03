#!/usr/bin/env python3
"""
SessionStart hook for the RunForLife coach plugin (Phase 1).

On every session start this hook primes Claude Code with the active athlete's
context so the coach is ready to reason without first re-reading disk:

  1. Read ~/.runforlife/active_athlete. If missing or empty, print guidance to
     run /switch and exit cleanly (no athlete is loaded — that's fine).
  2. Prune expired ephemeral context for the active athlete (dual-pruning: this
     hook + PostToolUse, since Stop can be missed on crash/Ctrl-C).
  3. Print a context block to stdout — Claude Code surfaces a SessionStart
     hook's stdout to the model as additional session context. The block is:
        [ACTIVE: <athlete>] banner
        a short profile summary
        the current (non-expired) ephemeral context

The hook is deliberately defensive: it must NEVER crash the session. Every step
is wrapped so any failure prints a short warning and exits 0. Plain text is
emitted (not the additionalContext JSON envelope) because plain stdout from a
SessionStart hook is reliably surfaced to the model.
"""

import sys
from pathlib import Path

# The plugin ships under the repo; the runforlife package lives in src/.
# hooks/ -> runforlife-coach/ -> repo root -> src
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC_DIR = _REPO_ROOT / "src"


def _ensure_src_on_path() -> None:
    """Make the runforlife package importable from the repo's src/ dir."""
    src = str(_SRC_DIR)
    if src not in sys.path:
        sys.path.insert(0, src)


def _read_active_athlete() -> str | None:
    """Return the active athlete name, or None if unset/empty/missing."""
    from runforlife.storage.paths import active_athlete_file

    path = active_athlete_file()
    if not path.exists():
        return None
    name = path.read_text(encoding="utf-8").strip()
    return name or None


def _profile_summary(profile: dict) -> list[str]:
    """Build a few human-readable lines summarizing the athlete profile.

    The profile schema varies between athletes, so every field is read
    defensively; missing fields are simply skipped.
    """
    lines: list[str] = []

    name = profile.get("name")
    if name:
        lines.append(f"Name: {name}")

    watch = profile.get("watch") or profile.get("context", {}).get("watch")
    if watch:
        lines.append(f"Watch: {watch}")

    age = profile.get("age")
    if age is not None:
        lines.append(f"Age: {age}")

    goals = profile.get("goals")
    if isinstance(goals, dict):
        goal_bits: list[str] = []
        hm = goals.get("half_marathon")
        if isinstance(hm, dict):
            target = hm.get("target_time")
            race_date = hm.get("race_date")
            goal_bits.append(
                "half-marathon "
                + " ".join(p for p in (target, f"by {race_date}" if race_date else None) if p)
            )
        hyrox = goals.get("hyrox")
        if isinstance(hyrox, dict):
            category = hyrox.get("category")
            race_date = hyrox.get("race_date")
            goal_bits.append(
                "Hyrox "
                + " ".join(p for p in (category, f"on {race_date}" if race_date else None) if p)
            )
        annual = goals.get("annual_run_days")
        if isinstance(annual, dict) and annual.get("target"):
            year = annual.get("year")
            goal_bits.append(
                f"{annual['target']} run days" + (f" in {year}" if year else "")
            )
        if goal_bits:
            lines.append("Goals: " + "; ".join(goal_bits))

    return lines


def _emit_context(athlete: str) -> None:
    """Print the [ACTIVE] banner, profile summary, and ephemeral context."""
    from runforlife.storage import athlete_memory

    print(f"[ACTIVE: {athlete}]")

    # Profile summary (best-effort; never fatal).
    try:
        profile = athlete_memory.load_profile(athlete)
        summary = _profile_summary(profile) if isinstance(profile, dict) else []
    except Exception as exc:  # noqa: BLE001 - never crash the session
        summary = []
        print(f"(warning: could not load profile: {exc})")
    if summary:
        print("\n## About You")
        for line in summary:
            print(f"- {line}")

    # Active ephemeral context (already pruned above).
    try:
        ephemeral = athlete_memory.load_active_ephemeral(athlete)
    except Exception as exc:  # noqa: BLE001 - never crash the session
        ephemeral = []
        print(f"(warning: could not load ephemeral context: {exc})")
    if ephemeral:
        print("\n## Current Context")
        for item in ephemeral:
            content = item.get("content")
            if not content:
                continue
            expires_on = item.get("expires_on")
            suffix = f" (until {expires_on})" if expires_on else ""
            print(f"- {content}{suffix}")


def main() -> int:
    """Run the hook. Always returns 0 so a failure never blocks the session."""
    try:
        _ensure_src_on_path()

        athlete = _read_active_athlete()
        if athlete is None:
            print(
                "[RunForLife] No active athlete set. "
                "Run /switch <tezuesh|kakul> to load an athlete's coaching context."
            )
            return 0

        # Prune expired ephemeral context before surfacing it (best-effort).
        try:
            from runforlife.storage import athlete_memory

            athlete_memory.prune_ephemeral(athlete)
        except Exception as exc:  # noqa: BLE001 - never crash the session
            print(f"[RunForLife] (warning: ephemeral prune skipped: {exc})")

        _emit_context(athlete)
        return 0
    except Exception as exc:  # noqa: BLE001 - last-resort guard, never crash
        print(f"[RunForLife] SessionStart hook warning: {exc}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
