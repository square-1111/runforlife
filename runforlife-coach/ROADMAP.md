# runforlife-coach — Improvement Roadmap

_Generated from a multi-agent audit (22 agents, 56 verified findings across 8 dimensions), 2026-06-13._

## Through-line
The coaching architecture (specialists, conflict ladder, self-evolution loop) is well-designed, but
it rests on a **data engine that is silently lossy and largely untested**, and several advertised
capabilities are wired to columns that are never populated. Fix ingest correctness and the storage
schema first — it unblocks nearly every higher-value analytics and specialist feature downstream.

## Biggest gaps
1. **No aerobic-progress metric** — EF / pace-at-fixed-HR / Z2-pace-trend don't exist. Banister CTL
   measures load, not capability. The base-builder's core question has no owner.
2. **Hyrox/strength unowned end-to-end** — no specialist, and all non-running activities are dropped
   at ingest, so station/strength load is invisible. Both athletes race Hyrox.
3. **Gap-row integrity bug** — partial Garmin fetches write all-NULL skeleton rows; sync checks
   existence not completeness and skips them forever, hiding real runs until a manual `--resync`.
4. **Stored-but-ignored signals** — readiness_score, deep/REM stages, HRV slope, Garmin baseline
   bands, body battery, stress are persisted yet never consumed by the readiness model.
5. **Self-evolution loop partly theatrical** — `/reflect` never writes insights.json; memory CLIs in
   SKILL.md don't exist; feedback captured from only one of three surfaces.
6. **Near-zero tests on the numeric engine** + no env-overridable `RUNFORLIFE_HOME` — tests/agents
   risk writing to real athlete data (the 2026-06 failure class).

## Cross-cutting bugs the audit surfaced
- `upsert_day` uses `INSERT OR REPLACE` and `to_row()` omits subjective fields → every `--resync`
  **wipes** subjective_readiness / life_context_note / session_rpe.
- ACWR divides by row-count, not 28 → inflated chronic load / understated ACWR on sparse windows.
- recovery-specialist prompt reasons over body-battery/stress/sleep-stages that readiness.py never returns.
- Isolation guard is Bash-only (Edit/Write/Read unguarded) and the pointer-write exception is a real bypass.
- UTC bedtime conversion may offset the stored `sleep_start_local`.

## Prioritized build order
| # | Item | Impact | Effort | Depends on |
|---|------|--------|--------|------------|
| 1 | Fix gap-row bug: completeness-aware sync skip + auto-reingest | high | M | — |
| 2 | Collector logging + per-row source provenance | high | M | 1 |
| 3 | `RUNFORLIFE_HOME` env override + validate `--user` + pure path getters | high | S | — |
| 4 | Store `run_is_indoor` at ingest (`run_temp_c` removed — no heat context in coaching) | high | M | — |
| 5 | Unit tests for ingest/readiness/banister/features | high | M | 3 |
| 6 | Efficiency Factor at ingest + `z2_pace_trend` skill | high | M | 4 |
| 7 | Add run pace/HR/vo2_max to correlate_metrics | medium | S | — |
| 8 | Harden isolation guard (read-only allowance, close bypass, cover Edit/Write) | high | M | — |
| 9 | `/compare` command + read-only athlete override | medium | M | 8 |
| 10 | Working memory CLIs (`--add-insight`, `--add-ephemeral`) + `/note` | high | M | — |
| 11 | Wire readiness to stored-but-ignored signals + reconcile specialist prompt | high | M | 5 |
| 12 | Capture non-running activities + Hyrox station benchmarks | high | L | 1 |
| 13 | Strength/Hyrox specialist + route it + propagate intensity_cap to conflict ladder | high | M | 12 |
| 14 | Close self-evolution loop: `/reflect` writes insights, full feedback capture | medium | M | 10 |
| 15 | Capture per-lap/split data **before 2026-07-01** | high | L | 1 |
| 16 | goal-status robustness (absent goals / past races) | medium | S | — |
| 17 | Banister load: prefer real Garmin/TRIMP load, unify definitions | medium | M | 12 |
| 18 | Goal feasibility verdict in goal-status / race-specialist | medium | M | — |
| 19 | Proactive anomaly surfacing in session_start / recovery-specialist | medium | M | 11 |
| 20 | `/chart` visualization (CTL/TSB, RHR/HRV, EF, Z2 pace) | medium | M | 6 |
| 21 | Injury-rehab / return-to-run specialist | medium | M | 10 |
| 22 | Specialist-scaffold script + conflict-rules.md single source | medium | M | 14 |
| 23 | Versioned schema migrations + fix UTC bedtime conversion | medium | M | 5 |
| 24 | n=1 experiment/intervention record + CLI | medium | L | 14 |
| 25 | Nutrition/fueling specialist | low | M | 22 |
| 26 | De-dup `_atomic_write_json` + tighten run_sql guard | low | S | — |

## Time-sensitive
Item **15** (per-lap capture) should land **before 2026-07-01** or the interval block's
rep-level data is lost forever. (Heat/temperature is deliberately not tracked — the coach
never uses it as an explanatory factor.)
