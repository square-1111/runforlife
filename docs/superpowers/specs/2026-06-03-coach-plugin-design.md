# RunForLife → Claude Code Plugin — Design Spec

**Date:** 2026-06-03
**Status:** Approved for planning
**Authors:** Tezuesh + Claude (brainstorming session)

## 1. Purpose

Reimplement the `runforlife` AI running coach as a **native Claude Code plugin** for two
athletes (Tezuesh + Kakul, Garmin FR165, 300-day running goal + Hyrox). Claude Code itself
becomes the coach (the reasoning LLM); the Python agent loop / coordinator / specialists are
replaced by Claude Code **skills + subagents**. Deterministic sports-science math and Garmin
sync stay as thin Python scripts invoked via Bash.

This serves the dual project goal: a working multi-athlete coach **and** a hands-on curriculum
in agent architecture (delegation → context isolation → parallel fan-out → conflict resolution
→ self-evolution).

## 2. Decisions (settled — do not relitigate)

| Decision | Choice |
|---|---|
| Integration model | Native Claude Code **plugin**; Claude Code IS the coach |
| Coaching structure | **Sub-skills + specialist subagents** (explicit multi-agent), not a monolith |
| Architecture | **CSSA** — Coordinator skill (instructions) → specialist **subagents** via Task tool |
| Multi-athlete | One machine, switch between `tezuesh` / `kakul`; isolated data + memory |
| Memory | Per-athlete **file-based**, 4 categories, read each session, rewritten as coach learns |
| Math + sync | Stay in Python, called via Bash; LLM never does arithmetic |
| Data migration | **Migrate** existing `data/<user>/` into `~/.runforlife/athletes/<user>/` |
| Sync trigger | **Both** — nightly scheduled (launchd) + on-demand stale-DB fallback |
| Token storage | **Disk**, `~/.runforlife/athletes/<name>/tokens/`, chmod 0600, gitignored |
| Personality store | Keep `personality.json`, **atomic write** (temp-file + `os.replace` + `fcntl` lock) |

### Binding architectural correction
In Claude Code **the running model is the orchestrator**. There is NO separate "coordinator
process" and NO hand-coded Haiku classifier + if/elif dispatcher. The coordinator is a
`SKILL.md` of **routing instructions** the main model follows; it routes by choosing which
specialist **subagent** to invoke (Task tool), driven by each subagent's *description*.
Subagents run in **isolated context** — the athlete name and needed context are **passed
explicitly** in the prompt, never inherited.

## 3. Component architecture

### 3.1 Plugin tree (versioned in repo)

```
runforlife-coach/
├── .claude-plugin/plugin.json      # manifest: declares skills/commands/agents/hooks
├── skills/
│   ├── coordinator/SKILL.md        # routing INSTRUCTIONS (not a classifier)
│   ├── memory/SKILL.md             # read/write the 4 athlete files; insight/feedback capture rules
│   ├── garmin-sync/SKILL.md        # Bash → runforlife.sync.nightly --user <a> [--start --end]
│   ├── readiness/SKILL.md          # Bash → runforlife.rag.readiness --user <a>   (NEW CLI)
│   ├── banister/SKILL.md           # Bash → runforlife.rag.banister  --user <a>   (NEW CLI)
│   └── conflict-rules.md           # plain-text EDITABLE priority ladder (tunable lesson)
├── commands/
│   ├── switch.md                   # /switch <tezuesh|kakul>
│   ├── daily-plan.md               # /daily-plan [athlete] [--date]
│   ├── weekly-plan.md              # /weekly-plan [athlete] [--start]
│   ├── goal-status.md              # /goal-status [athlete]
│   └── personality.md              # /personality [athlete]  (inspect learned style — debug)
├── agents/
│   ├── recovery-specialist.md      # sleep/HRV/body-battery/stress/readiness; scoped tools
│   ├── training-specialist.md      # volume/ACWR/intensity/zones/consistency; scoped tools
│   ├── race-specialist.md          # VO2max/predictions/goal-gap/taper; scoped tools
│   ├── analytics-specialist.md     # correlate_metrics / run_sql; flags thin data (<30 pts)
│   ├── conflict-resolver.md        # Phase 3: arbitrates per conflict-rules.md
│   └── parallel-fetch.md           # read-only multi-metric Garmin fan-out (NO memory writes)
├── hooks/
│   ├── session_start.py            # load active athlete + 4 files; PRUNE ephemeral; precompute+cache
│   │                               #   readiness/banister; print [ACTIVE: tezuesh] banner
│   ├── pre_tool_use.py             # inject active athlete into data/memory tools; FAIL LOUD if unset
│   ├── post_tool_use.py            # eager prune_expired; buffer behavioral signals; validate writes
│   └── stop.py                     # persist insights/feedback; atomic personality update; final prune
├── scripts/
│   ├── athlete_init.py             # one-time: create ~/.runforlife/athletes/<name>/ + seed 4 files
│   ├── migrate_data.py             # one-time: data/<user>/ → ~/.runforlife; split memories → 4 files
│   └── memory_manager.py           # CLI: --list/--show/--delete/--prune-expired (audit/debug)
└── .mcp.json                       # optional; not required for v1
```

Plugin code is versioned in the repo. **Athlete data lives outside the plugin** under
`~/.runforlife/` so it survives plugin updates and is never committed.

### 3.2 Per-athlete data layout (`~/.runforlife/`)

```
~/.runforlife/
├── active_athlete                  # durable sticky pointer: "tezuesh"
└── athletes/<name>/
    ├── profile.json                # STATIC: name, age, watch, goals (sub-HM time+date, Hyrox
    │                               #   partner+date, 300-day annual), prefs. Coach NEVER writes.
    ├── insights.json               # [{insight, confidence, type, discovered, last_reinforced}]
    ├── ephemeral.json              # [{content, expires_on, created_at}] travel/injury/life
    ├── feedback.json               # [{date, advice_type, advice, rating, adherence, outcome}]
    ├── personality.json            # signal-counting model (atomic writes)
    ├── metrics.db                  # synced Garmin daily_metrics + activities (SQLite, WAL)
    ├── banister.json               # cached Banister state
    └── tokens/                     # garth session tokens, chmod 0600, gitignored
```

**The 4 memory categories** (the user's decided scope):
1. **profile.json** — Profile & goals (static; coach reads, never overwrites)
2. **insights.json** — Learned insights (patterns the coach discovers)
3. **ephemeral.json** — Ephemeral context with `expires_on` (auto-pruned)
4. **feedback.json** — Coaching feedback (tunes future advice)

## 4. Data flow

### 4.1 Delegation flow (per query)
1. **SessionStart hook** reads `~/.runforlife/active_athlete` (if unset → prompt `/switch`).
   Loads the 4 files, **prunes expired ephemeral**, precomputes + caches readiness/banister,
   injects an `## About You` context block.
2. Main model follows `coordinator/SKILL.md`:
   - **Single-domain** ("how did I sleep?") → invoke ONE specialist subagent (Task tool),
     passing athlete name explicitly.
   - **Cross-domain** ("should I run today?") → invoke recovery + training (Phase 3: parallel).
     On agreement → synthesize. On conflict → apply `conflict-rules.md` and **show which signal
     won and why** (Phase 3: delegate to `conflict-resolver`).
3. Each specialist runs isolated with its own **scoped tool subset**, returns final text.
4. **PreToolUse hook** injects active athlete into every data/memory tool; **fails loudly** if
   unset → tezuesh/kakul data can never mix.
5. **PostToolUse hook** eagerly `prune_expired`, buffers signals, validates `remember` writes.
6. **Stop hook** persists insights/feedback, atomic personality update, final prune.

### 4.2 Math + sync (Python via Bash; LLM never computes)
- `garmin-sync` → `uv run python -m runforlife.sync.nightly --user <a> [--start --end]` (CLI exists).
- `readiness` → `uv run python -m runforlife.rag.readiness --user <a>` — **ADD argparse `__main__`**
  wrapping `compute_readiness(user, target_date)` → emits JSON `{score, tier, conflict_detected, components}`.
- `banister` → `uv run python -m runforlife.rag.banister --user <a>` — **ADD argparse `__main__`**
  wrapping `compute_banister(user)` → emits JSON.
- Specialists read cached metrics; **fall back to live Garmin on empty DB** — never conclude "no
  training." Carry the existing guardrail verbatim (`specialists.py:162-164, 228-230`).
- **Cache** readiness/banister once per session; recompute only after a fresh sync (avoids repeated
  cold `uv` startups mid-conversation).

### 4.3 Sync triggers (both)
- **Scheduled:** per-athlete nightly launchd job runs `runforlife.sync.nightly`.
- **On-demand:** a specialist detecting a stale DB (or `/garmin-sync`) triggers a sync.

## 5. Self-improvement loop (real, bounded, auditable)

- **Capture:** specialists call `remember`; PostToolUse buffers behavioral signals.
- **Personality:** Stop hook calls the existing signal-counter (`update_personality` →
  `_maybe_promote` at ≥3 signals & ≥60% share; confidence `min(1.0, n/20)`), written **atomically**.
  `coaching_style_block()` injects style into every specialist prompt next session.
- **Feedback:** `/feedback` or end-of-session prompt appends to `feedback.json`; SessionStart
  surfaces recent negative ratings to adjust intensity.
- **Conflict-rule evolution:** the learner edits `conflict-rules.md` in plain text and watches
  outcomes in `feedback.json` — bounded, no opaque self-modification.

## 6. Required code changes to existing repo

| File | Change |
|---|---|
| `storage/paths.py` | Repoint `DATA_DIR/<user>` → `~/.runforlife/athletes/<user>/` |
| `storage/memory_store.py` | Replace single `memories` table with 4 explicit category files |
| `storage/personality_store.py` | Make `save_personality` atomic (temp + `os.replace` + `fcntl` lock) |
| `rag/readiness.py` | Add argparse `__main__` CLI emitting JSON |
| `rag/banister.py` | Add argparse `__main__` CLI emitting JSON |
| `agent/specialists.py` | Preserve empty-DB guardrail verbatim; port persona text into `agents/*.md` |
| `sync/nightly.py` | CLI already present — reuse as-is |

## 7. Phased build order (mapped to learning goals)

- **Phase 1 — Single-specialist delegation (the spine).** Manifest + 4 specialist subagents +
  `coordinator/SKILL.md` (description-based routing to ONE subagent). 4-file memory +
  `garmin-sync`/`readiness`/`banister` Bash skills (write the 2 missing CLIs first). `/switch` +
  durable `active_athlete` + SessionStart banner. Migration script.
  *Teaches:* subagent invocation, context isolation, tool scoping, file memory, athlete switching.
- **Phase 2 — Hooks, safety, personalization.** All 4 hooks; wire `coaching_style_block`. Add
  `/daily-plan`, `/weekly-plan`, `/goal-status`, `/personality`.
  *Teaches:* lifecycle hooks, durable/auditable memory, crash-safe persistence, "agent learns."
- **Phase 3 — Parallel fan-out + conflict resolution (the payoff).** Fan out recovery+training in
  parallel on cross-domain queries; `conflict-resolver` subagent driven by editable
  `conflict-rules.md`; read-only `parallel-fetch` subagent.
  *Teaches:* parallel delegation, conflict arbitration, the latency/quality trade-off.
- **Phase 4 — Self-evolution (stretch).** Weekly reflection skill mining `feedback.json` for
  success-rate-by-advice-type → proposes (user-approved) edits to `conflict-rules.md` / specialist
  prompts. Optional skill-gap detection (recurring nutrition Qs → propose `nutrition-specialist`).
  *Teaches:* measurable, transparent, opt-in self-improvement.

## 8. Confirmed defaults (soft questions)

- **Conflict resolver:** inline in coordinator for Phase 3; promote to dedicated subagent only if
  the lesson warrants it.
- **Fan-out trigger:** only on genuinely cross-domain queries (`/daily-plan`, "should I run
  today?"); single-specialist otherwise. This is the key latency lever.
- **Ephemeral TTL defaults** (when coach writes an entry without an explicit date): travel =
  explicit end-date; injury = 7 days; mood/stress = 3 days.

## 9. Risks / failure modes to guard

- **Athlete data mix** → PreToolUse athlete injection + fail-loud guard; explicit athlete arg to
  every subagent.
- **Stale ephemeral context poisoning advice** → dual pruning (SessionStart + PostToolUse), not
  Stop-only (Stop misses crashes/Ctrl-C).
- **Lost personality writes** → atomic temp + `os.replace` + lock.
- **Subagent latency on common queries** → fan out only when cross-domain; cache scores per session.
- **LLM arithmetic** → all math in Python scripts; specialists read JSON, never compute.

## 10. Out of scope (v1)

- MCP server (`.mcp.json` optional, deferred).
- macOS Keychain token storage (disk + chmod 0600 chosen).
- Cross-machine sync of `~/.runforlife/` (single-machine multi-athlete only).
