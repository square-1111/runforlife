#!/usr/bin/env python3
"""
SessionStart hook for the RunForLife coach plugin (Phase 1 + Phase 2).

On every session start this hook primes Claude Code with the active athlete's
context so the coach is ready to reason without first re-reading disk:

  1. Read ~/.runforlife/active_athlete. If missing or empty, print guidance to
     run /switch and exit cleanly (no athlete is loaded — that's fine).
  2. Prune expired ephemeral context for the active athlete (dual-pruning: this
     hook + PostToolUse, since Stop can be missed on crash/Ctrl-C).
  3. Precompute readiness + Banister state once per session, cache them to
     ~/.runforlife/athletes/<a>/.session_cache.json (atomic write), and print a
     one-line summary of each into the context block. Caching here avoids
     repeated cold `uv` startups when specialists need these scores mid-chat.
  4. Append the learned coaching-style block (personality model) once it has
     enough confidence (>=0.2) so every session reflects what the coach learned.
  5. Print a context block to stdout — Claude Code surfaces a SessionStart
     hook's stdout to the model as additional session context. The block is:
        [ACTIVE: <athlete>] banner
        a short profile summary
        the current (non-expired) ephemeral context
        today's readiness + Banister one-liners
        the learned coaching-style block (when confident)

The hook is deliberately defensive: it must NEVER crash the session. Every step
is wrapped so any failure prints a short warning and exits 0. Plain text is
emitted (not the additionalContext JSON envelope) because plain stdout from a
SessionStart hook is reliably surfaced to the model.
"""

import json
import os
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


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Write JSON atomically: temp file in the same dir + os.replace.

    A same-directory temp file guarantees os.replace is an atomic rename on
    POSIX, so a reader never sees a half-written cache file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _precompute_and_cache(athlete: str) -> None:
    """Compute readiness + Banister, cache them, and print one-line summaries.

    Each computation is independently guarded: a failure in one must not
    suppress the other, and neither may ever crash the session. The combined
    result is cached to ~/.runforlife/athletes/<a>/.session_cache.json so
    specialists can read it without re-running cold `uv` invocations.
    """
    from runforlife.storage.paths import athlete_dir

    cache: dict = {}

    # Readiness — always available (degrades to "insufficient data" internally).
    try:
        from runforlife.rag.readiness import compute_readiness

        readiness = compute_readiness(athlete)
        cache["readiness"] = {
            "score": readiness.score,
            "tier": readiness.tier,
            "summary_line": readiness.summary_line,
            "conflict_detected": readiness.conflict_detected,
            "components": readiness.components,
        }
        print("\n## Today's Readiness")
        print(f"- {readiness.summary_line}")
    except Exception as exc:  # noqa: BLE001 - never crash the session
        print(f"(warning: could not compute readiness: {exc})")

    # Banister — returns None on < 14 days of data; guard accordingly.
    try:
        from runforlife.rag.banister import compute_banister

        banister = compute_banister(athlete)
        if banister is not None:
            cache["banister"] = {
                "fitness": banister.fitness,
                "fatigue": banister.fatigue,
                "tsb": banister.tsb,
                "trend": banister.trend,
                "overreaching_risk": banister.overreaching_risk,
                "summary": banister.summary,
            }
            print("\n## Training Load (Banister)")
            print(f"- {banister.summary}")
        else:
            cache["banister"] = None
            print("\n## Training Load (Banister)")
            print("- Insufficient data (need 14+ days of metrics).")
    except Exception as exc:  # noqa: BLE001 - never crash the session
        print(f"(warning: could not compute Banister state: {exc})")

    # Cache the combined result (best-effort; a cache failure is non-fatal).
    try:
        cache_path = athlete_dir(athlete) / ".session_cache.json"
        _atomic_write_json(cache_path, cache)
    except Exception as exc:  # noqa: BLE001 - never crash the session
        print(f"(warning: could not write session cache: {exc})")


def _emit_coaching_style(athlete: str) -> None:
    """Append the learned coaching-style block when the model is confident.

    coaching_style_block() already returns "" until confidence >= 0.2, so we
    only print anything (header included) when it has something to say.
    """
    try:
        from runforlife.storage.personality_store import coaching_style_block

        block = coaching_style_block(athlete)
        if block and block.strip():
            print(block)
    except Exception as exc:  # noqa: BLE001 - never crash the session
        print(f"(warning: could not load coaching style: {exc})")


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

    # Precompute + cache readiness/Banister and surface one-liners (best-effort).
    _precompute_and_cache(athlete)

    # Append the learned coaching-style block when confident (best-effort).
    _emit_coaching_style(athlete)


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
