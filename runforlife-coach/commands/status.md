---
description: Quick, cheap status check on an athlete — "what's he up to these days?", "am I improving?", momentum this week. Fetches the numbers ONCE (analytics + parallel-fetch), then answers directly with a numbers-first momentum block and ONE next action. No lens fan-out — use /panel only for genuinely cross-domain trade-offs.
argument-hint: "[athlete] [--date YYYY-MM-DD]"
---

# /status — quick numbers + one next action (the cheap path)

Raw arguments: **$ARGUMENTS**

This is the lightweight default for status/momentum questions ("what's he up to?", "am I
improving?", "how's this week going?"). It spawns just the two read-only data-gatherers and answers
directly — it does NOT convene the interpretation panel. Reserve `/panel` for genuinely cross-domain
calls (training + recovery + physio + strength trading off against each other). Numbers first, no
LLM arithmetic — every figure comes from a subagent's read, never from you.

## 1. Resolve the athlete

Parse `$ARGUMENTS` (order-independent; the athlete is the FIRST non-flag word).

1. **If an athlete token is present**, it MUST be exactly `tezuesh` or `kakul` (case-sensitive).
   Otherwise **STOP**:

   > Invalid athlete `<what they passed>`. Usage: `/status [tezuesh|kakul] [--date YYYY-MM-DD]`.

2. **If no athlete token is present**, read `~/.runforlife/active_athlete`. If it prints `tezuesh`
   or `kakul`, use it. If missing/empty, **STOP**:

   > No active athlete set. Run `/switch <tezuesh|kakul>` first, or pass the name: `/status tezuesh`.

3. Hold the resolved name as `<athlete>` and pass it explicitly to every subagent — never let one
   infer it.

## 2. Date

If a `--date YYYY-MM-DD` flag is present, validate it is a real date and hold it as `<date>`;
otherwise use today.

## 3. Empty-DB guardrail (carry verbatim — do NOT skip)

If `~/.runforlife/athletes/<athlete>/metrics.db` is missing or has no rows, the DB is **unsynced** —
this does NOT mean the athlete hasn't trained or is fully recovered. **Never** conclude "no
training," "no data," or "fully recovered" from an empty DB. Tell the athlete the data looks
unsynced, suggest `/garmin-sync`, and STOP — do not fabricate a status.

## 4. Data freshness — auto-sync the gap before reading (do NOT skip)

1. Read the latest date on file:

   ```bash
   sqlite3 ~/.runforlife/athletes/<athlete>/metrics.db \
     "SELECT MAX(date) FROM daily_metrics WHERE user_id='<athlete>';"
   ```

2. **If it is older than yesterday**, backfill the gap yourself (do NOT ask the athlete to sync by
   hand):

   ```bash
   cd "$(cat ~/.runforlife/repo_path)" && uv run python -m runforlife.sync.nightly --user <athlete> --start <day-after-latest> --end <today>
   ```

   Garmin is rate-limited, so a multi-day range runs for a while. Already-ingested days are skipped —
   re-running never double-counts.

3. **If the sync fails** (`[AUTH FAILED]`, a traceback, non-zero exit): do NOT fabricate today's
   numbers. Note it may need a re-auth (`cd "$(cat ~/.runforlife/repo_path)" && uv run python -m
   runforlife.auth <athlete>`) and proceed with an explicit **"as of `<latest date>`"** caveat on
   every figure.

4. The empty-DB guardrail (§3) still governs: a missing/zero-row DB → follow §3 and STOP. Auto-sync
   only backfills a gap on a DB that already has data.

## 5. Fetch the numbers ONCE

Spawn these **two read-only data-gatherers in parallel** (single message), passing `<athlete>` and
`<date>` explicitly into each prompt (they run in isolated context and inherit nothing):

- **analytics-specialist** — build the numeric bundle: the four momentum rows (spec below),
  runs-done this ISO week, the last ~10-day run log, latest ACWR, and weekly km totals. Numeric
  backbone — leave it on its default (capable) model.
- **parallel-fetch** — readiness (score/tier + driving components), banister (fitness/fatigue/form),
  and any non-expired ephemeral entries (injury/illness/travel/plan template).

That is the entire fan-out. Do NOT spawn the interpretation lenses — if the answer genuinely needs a
recovery-vs-training trade-off, say so and suggest `/panel`.

## 6. Answer directly — numbers-first, one next action

You arrange and translate the fetched numbers; you never compute, round, or estimate them. Use this
structure:

```
# <one warm, honest headline — the answer + the momentum in plain words>

**Where you are this week:** <X> of <N planned> runs done · <M> to go · <this week's km so far> km · readiness <score>/<10> (<tier>)
<if no live plan item: "No live plan on file — showing completed work only." and omit the M-to-go figure.>
<if unsynced and not backfilled: caveat every figure "as of <latest date>"; if the DB was empty, you already STOPPED at §3.>

## Momentum — this week (partial) vs the last 2 weeks
| Metric            | 2 wks ago | last wk | this wk    | trend        |
|-------------------|-----------|---------|------------|--------------|
| Runs / km         | <n>/<km>  | <n>/<km>| <n>/<km>*  | <↑/→/↓ + word> |
| Easy pace (min/km)| <p>       | <p>     | <p>        | <faster/flat/slower by X s/km> |
| EF (pace-at-HR)   | <ef>      | <ef>    | <ef>       | <engine up/flat/down> |
| Cadence (spm)     | <c>       | <c>     | <c>        | <toward/away from target> |
<* this week is partial — km/runs compared through the same weekday as prior weeks.>

**The good news (earned):** <one specific, quantified win>

**The honest bit:** <one specific, quantified limiter — the gap, not a verdict on the athlete>

## Do this next
<ONE clear, high-leverage action for the next session / rest of the week>

## Toward sub-60 Hyrox Pro
<honest one-liner tying this week to the north star — moves toward it, holds, or costs, and why>
```

### Week-over-week momentum spec (numbers come from the analytics read, never your math)

Group runs by ISO week (Mon–Sun). Compare the CURRENT ISO week (Monday 00:00 → `<date>`, inclusive)
against the previous **2 full ISO weeks** (fall back to 1 if only one exists; if zero prior weeks,
say "first week of tracked data — no trend yet" and skip the table).

- **Partial week:** never compare partial-week TOTALS against full-week totals. For volume (runs/km),
  compare **cumulative-through-the-same-weekday** and mark the column `* through <weekday>`. Per-run
  quality metrics (easy pace, EF, cadence) use the weekly average as-is.
- **Four rows, all from `ran_today=1`:**
  1. **Runs / km** — `COUNT(*)` and `ROUND(SUM(run_distance_km),1)` (partial week = same-weekday
     cumulative).
  2. **Easy pace** — `AVG(run_avg_pace_sec_per_km)` over EASY runs only (exclude quality/interval/
     long efforts so pace isn't polluted); report min/km. Lower = faster.
  3. **EF (pace-at-HR proxy)** — `AVG(run_efficiency_factor)`; higher = engine improving. NULL on a
     week → report `n/a`, don't drop the row.
  4. **Cadence** — `AVG(run_avg_cadence)` spm; frame movement **toward the target cadence** as
     improvement (active cadence-retraining directive), not just up/down.
- State BOTH numbers for any called-out change (`EF <old> → <new>`) and the delta in the metric's own
  unit (`pace -6 s/km`). Name at least ONE improvement explicitly; report regression just as plainly,
  framed as a fixable gap.
- **ACWR is a safety sidecar:** if latest `acwr` is outside ~0.8–1.3, add one caution line; else omit.

### Runs-left-vs-plan

Read the non-expired `items[].content` in `~/.runforlife/athletes/<athlete>/ephemeral.json` (honor
`expires_on`). Count the week's SCHEDULED run sessions from the free-text template (rest/mobility
days don't count). `runs_done` = `COUNT(ran_today=1)` this ISO week (from the analytics read);
`runs_left` = `planned_runs − runs_done` (floor 0). If no non-expired plan item, say "no live plan on
file — showing completed work only" and omit the M-to-go figure.

### Guardrails (carry verbatim)

- **No-heat:** never attribute any pace/EF/HR change to temperature; never gate on `run_temp_c`.
- **Empty-DB / unsynced:** an unsynced or empty DB never means "no training" or "fully recovered" —
  honor §3/§4. If §4 could not backfill, caveat every figure "as of `<latest date>`".
- **Stale-readiness placeholder:** a readiness of ~5.0 / Amber with every component == 0.5 and all
  additive flags null is the "no data for that day" signature — report it as "no readiness data for
  that day," not a real Amber.
- **Cross-domain escalation:** if the honest answer needs a recovery-vs-training-vs-physio trade-off,
  don't force it here — give the numbers and suggest `/panel <athlete> <question>`.
