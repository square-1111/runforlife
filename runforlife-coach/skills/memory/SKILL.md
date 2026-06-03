---
name: memory
description: When and how to read and write the active athlete's 4 memory files (profile, insights, ephemeral, feedback). Use when capturing a learned pattern, recording a time-boxed life fact (travel/injury/mood), logging the athlete's reaction to advice, or inspecting/auditing stored memory. Never writes profile.json.
---

# Athlete Memory

Each athlete owns a tiny file-based memory under `~/.runforlife/athletes/<athlete>/`.
There are exactly **four** files, each with a distinct job. The coach reads them to
personalize advice and writes back to three of them as it learns. The fourth
(`profile.json`) is **read-only**.

The active athlete is loaded automatically at **SessionStart** (the hook reads all four
files, prunes expired ephemeral entries, and injects an `## About You` block). You do not
need to read the files manually at the start of a session — the context is already present.
Use this skill when you need to **write** a new memory, or to **inspect/audit/clean** what is
already stored mid-session.

## The 4 files

### 1. `profile.json` — static baseline (READ-ONLY)
Name, age, watch, goals (sub-HM target time + date, Hyrox partner + date, the 300-day annual
goal), and preferences. This is the ground truth the athlete set up.
**Never write to `profile.json` from this skill or any tool.** If the athlete's goals or prefs
truly changed, that is an explicit setup action the athlete performs — not something the coach
infers. Treat it as immutable input.

### 2. `insights.json` — patterns the coach discovers
Durable, evidenced observations about how this athlete responds to training and recovery
(e.g. "sleep below 6h reliably drops next-day readiness"). Each entry carries a `confidence`
(0.0–1.0), a `type`, a `discovered` date, and a `last_reinforced` date.
Write via `add_insight`.

**Capture rule — evidence, not speculation.** Only record an insight when a pattern is actually
**evidenced** by the data or by repeated observation. A single coincidence or a hunch is not an
insight. If you are guessing, do not write it. Start new insights at a modest confidence
(default `0.5`) and let reinforcement raise it over time.

### 3. `ephemeral.json` — time-boxed life facts (auto-pruned)
Short-lived context that should influence advice *now* but must not poison it later: travel,
illness, injuries, work stress, mood. Every entry has an `expires_on` date (`YYYY-MM-DD`) or
`null` for "no known end." Expired entries are pruned automatically (SessionStart, and again by
the Phase 2 PostToolUse hook), so you never have to remember to delete them.
Write via `add_ephemeral`.

**TTL rule — always set a sensible expiry:**
| Kind of fact | `expires_on` |
|---|---|
| Travel | the **explicit end date** of the trip |
| Injury | **today + 7 days** (re-add if it persists) |
| Mood / stress | **today + 3 days** |
| Genuinely open-ended | `null` (use sparingly) |

Prefer a real date over `null`. A short TTL that gets re-added is safer than a stale fact that
silently skews advice for weeks.

### 4. `feedback.json` — athlete reactions to advice
How the athlete responded to coaching: a `rating` (e.g. positive/negative/neutral), optional
`adherence` (did they follow it?), and optional `outcome` (what happened). This tunes future
advice — SessionStart surfaces recent negative ratings so the coach can adjust.
Write via `add_feedback`.

## Python API

All reads and writes go through `runforlife.storage.athlete_memory`. Writes are atomic
(temp file + `os.replace`) and ids auto-increment per file.

```python
from runforlife.storage import athlete_memory as mem

mem.load_profile(user)                  # dict (read-only baseline)

mem.load_insights(user)                 # list[dict]
mem.add_insight(user, insight, type, confidence=0.5)        # -> int id

mem.load_active_ephemeral(user)         # list[dict] — only non-expired
mem.add_ephemeral(user, content, expires_on)                # expires_on: "YYYY-MM-DD" | None -> int id
mem.prune_ephemeral(user)               # -> int count deleted

mem.load_feedback(user)                 # list[dict]
mem.add_feedback(user, advice_type, advice, rating, adherence=None, outcome=None)  # -> int id
```

Prefer the CLI below for routine inspect/modify so behavior stays consistent and auditable.

## CLI — `memory_manager.py`

Run from the repo root (`/Users/tezueshvarshney/work/test/runforlife`). Replace `<a>` with the
active athlete (`tezuesh` or `kakul`).

```bash
# Inspect everything for an athlete (all 4 files)
uv run python /Users/tezueshvarshney/work/test/runforlife/runforlife-coach/scripts/memory_manager.py --user <a> --list

# Show one category (profile | insights | ephemeral | feedback)
uv run python /Users/tezueshvarshney/work/test/runforlife/runforlife-coach/scripts/memory_manager.py --user <a> --show insights

# Add a discovered insight (only when evidenced)
uv run python /Users/tezueshvarshney/work/test/runforlife/runforlife-coach/scripts/memory_manager.py \
  --user <a> --add-insight "Readiness drops sharply after <6h sleep" --type recovery --confidence 0.5

# Add a time-boxed ephemeral fact (always set an expiry; see TTL rule)
uv run python /Users/tezueshvarshney/work/test/runforlife/runforlife-coach/scripts/memory_manager.py \
  --user <a> --add-ephemeral "Travelling to Berlin, limited running" --expires-on 2026-06-14

# Add feedback on advice the athlete reacted to
uv run python /Users/tezueshvarshney/work/test/runforlife/runforlife-coach/scripts/memory_manager.py \
  --user <a> --add-feedback "Suggested easy day after poor sleep" --advice-type recovery \
  --rating positive --adherence followed --outcome "felt fresh next session"

# Delete a single entry by id from a category
uv run python /Users/tezueshvarshney/work/test/runforlife/runforlife-coach/scripts/memory_manager.py \
  --user <a> --delete insights --id 3

# Prune expired ephemeral entries (also runs automatically at SessionStart)
uv run python /Users/tezueshvarshney/work/test/runforlife/runforlife-coach/scripts/memory_manager.py \
  --user <a> --prune-expired
```

## Rules (summary)

- **Never write `profile.json`.** It is the athlete's static baseline.
- **Insights:** capture only what is **evidenced** by data or repeated observation — never
  speculation. New insights start at `confidence=0.5`.
- **Ephemeral:** always set a sensible `expires_on` — travel = explicit trip end date,
  injury = +7 days, mood/stress = +3 days; reserve `null` for genuinely open-ended facts.
  Expired entries are pruned automatically; you do not delete them by hand.
- **Feedback:** record the athlete's real reaction (rating, and adherence/outcome when known)
  so future advice can adapt.
- **Reads are automatic at SessionStart.** Use this skill to write new memory or to
  inspect/clean existing memory mid-session.
