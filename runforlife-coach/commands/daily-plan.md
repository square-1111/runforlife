---
description: Decide today's single concrete training call for an athlete — run y/n, type, distance, target pace, HR zone, and a 1-2 line rationale — by fanning out to the recovery and training specialists and synthesizing one recommendation.
argument-hint: "[athlete] [--date YYYY-MM-DD]"
---

# /daily-plan — today's one concrete training call

Raw arguments: **$ARGUMENTS**

This is a genuinely cross-domain question ("what should I do today?"). It needs BOTH a recovery
read and a training-load read, then ONE synthesized call. Follow the steps in order. Numbers
first, no LLM arithmetic — all math comes from the deterministic scripts.

## 1. Resolve the athlete

Parse `$ARGUMENTS`. It may contain an athlete name, a `--date YYYY-MM-DD` flag, both, or neither
(order-independent).

1. **If an athlete token is present** (the first non-flag word): it MUST be exactly `tezuesh` or
   `kakul` (case-sensitive). If it is anything else, **STOP** and reply:

   > Invalid athlete `<what they passed>`. Usage: `/daily-plan [tezuesh|kakul] [--date YYYY-MM-DD]`.

2. **If no athlete token is present**, read the active athlete pointer:

   ```bash
   cat ~/.runforlife/active_athlete 2>/dev/null
   ```

   - If it prints `tezuesh` or `kakul`, use that.
   - If the file is missing or empty, **STOP** and reply:

     > No active athlete set. Run `/switch <tezuesh|kakul>` first, or pass the name: `/daily-plan tezuesh`.

3. Hold the resolved name as `<athlete>` for every step below. Always pass it explicitly — never
   let a subagent infer it.

## 2. Resolve the target date

Parse a `--date YYYY-MM-DD` flag from `$ARGUMENTS`.

- If present, validate it is a real `YYYY-MM-DD` date and use it as `<date>`.
- If absent, use today (the current date). Leave the `--date` flag off the readiness command so it
  defaults to today.

## 3. Gather the deterministic inputs (run these exactly)

Run these from the repo root. They print JSON / rows — never compute scores yourself.

### 3.0 Auto-sync freshness check (run FIRST, before readiness/banister)

Today's call must use today's data. Before reading readiness/banister, check how fresh the local DB
is and top it up automatically if it is stale.

1. Read the latest ingested day for the user:

   ```bash
   sqlite3 ~/.runforlife/athletes/<athlete>/metrics.db \
     "SELECT max(date) FROM daily_metrics WHERE user_id = '<athlete>';"
   ```

2. If that latest date is **older than yesterday** (i.e. there is a gap between the day after it and
   `<date>`/today), AUTOMATICALLY pull the missing range before doing anything else:

   ```bash
   cd /Users/tezueshvarshney/work/test/runforlife && uv run python -m runforlife.sync.nightly \
     --user <athlete> --start <day-after-latest> --end <today>
   ```

   Already-ingested days are skipped, so this is safe to run. A wide range can take minutes (Garmin
   is rate-limited) — that is expected; let it finish, then re-read the latest date.

3. **On sync failure** (the command errors, or the range still does not reach yesterday): do NOT
   fabricate a plan. Fall back to the existing empty-DB / unsynced guardrail in §4, and if you still
   proceed on the most recent synced day, caveat every number with an explicit "as of <latest date>"
   so the athlete knows the call is not built on today's data. Keep the guardrail intact.

If the latest date already reaches yesterday (or `<date>`), the DB is fresh — skip the sync and
continue.

### 3.1 Deterministic reads

**Readiness** (recovery state for the target day):

```bash
cd /Users/tezueshvarshney/work/test/runforlife && uv run python -m runforlife.rag.readiness --user <athlete>
```

If a `--date` was given, append it: `... -m runforlife.rag.readiness --user <athlete> --date <date>`.
Output JSON: `{score, tier, conflict_detected, components}`.

**Banister** (fitness / fatigue / training-load state):

```bash
cd /Users/tezueshvarshney/work/test/runforlife && uv run python -m runforlife.rag.banister --user <athlete>
```

**Recent training context** — read the synced metrics for recent run history (distance, pace, avg
HR, ACWR) so the prescription is grounded in what they have actually been doing:

```
~/.runforlife/athletes/<athlete>/metrics.db
```

**Scheduled interval-block plan** — read the active training template so today's call ALIGNS to the
block the athlete is actually on (not an invented one):

```bash
cat ~/.runforlife/athletes/<athlete>/ephemeral.json
```

The plan lives in `items[].content` as **free text** (e.g. an INTERVAL BLOCK with a weekly template
like `Mon rest+mobility | Tue QUALITY | Wed leg day+easy | ... | Sun long run easy`, a 4-week rep/pace
split, and easy/long-run paces). Only honor items whose `expires_on` is **not yet past** `<date>`;
ignore expired items. Do NOT parse or reinterpret the numbers yourself — pass the raw non-expired
`content` verbatim to the training-specialist and let it work out (a) which weekday `<date>` maps to
in the template (quality / leg / long / rest slot), and (b) which week of the 4-week split is current,
so it reads off the prescribed reps/paces rather than inventing them. If there is no non-expired
interval-block item, say so and let the specialist fall back to goal-phase defaults.

**Last 7 days of completed sessions** — read what the athlete has ALREADY trained this week so today's
call does not double up (e.g. don't prescribe a second quality session if this week's was already run):

```bash
sqlite3 -header -column ~/.runforlife/athletes/<athlete>/metrics.db \
  "SELECT date, ran_today, run_distance_km, run_avg_pace_sec_per_km, run_avg_hr,
          run_avg_cadence, run_efficiency_factor, acwr
   FROM daily_metrics
   WHERE user_id = '<athlete>' AND date >= date('<date>', '-7 days') AND date <= '<date>'
   ORDER BY date;"
```

There is **no** `run_duration` column — derive duration deterministically as
`run_distance_km * run_avg_pace_sec_per_km / 3600` (hours). Pass these rows to the training-specialist
so it can tell, numbers-first, which of this week's template slots (especially the QUALITY session)
have already been completed and adjust today's prescription accordingly. Do not do this arithmetic in
the LLM — hand the rows and the derivation rule to the specialist.

## 4. Empty-DB guardrail (carry verbatim — do NOT skip)

If the readiness or banister scripts error, return no score, or the metrics DB has no rows, the
local DB is **unsynced** — this does NOT mean the athlete has not trained or is fully recovered.
**Never** conclude "no training," "no data," or "fully recovered" from an empty DB. Instead, tell
the athlete the data looks unsynced, suggest they run `/garmin-sync` to pull fresh Garmin data,
and STOP — do not fabricate a plan. Re-run `/daily-plan` once synced.

## 5. Fan out to the specialists IN PARALLEL (pass the athlete name explicitly)

Invoke BOTH subagents via the Task tool **in a single message** so they run concurrently — do not
wait for one to finish before starting the other. In each prompt, state the athlete name and the
target date explicitly, and ask for their domain call for today:

- **recovery-specialist** — assess `<athlete>` for `<date>` and return its REST / EASY / GO call
  with the readiness score, tier, and the 2-3 driving metrics.
- **training-specialist** — assess `<athlete>` for `<date>` and return the next-session
  prescription (type, distance, target pace, HR zone) gated by ACWR band and goal phase. Pass it,
  in the prompt text, (a) the raw non-expired scheduled interval-block `content` from §3.1 so it
  aligns today to the correct weekday slot and 4-week split week, and (b) the last-7-days completed
  sessions rows plus the duration derivation rule so it knows what has already been trained this
  week (especially whether the QUALITY session is already done) and does not double-prescribe.
  Numbers-first, no-heat: never explain pace/EF/HR via heat or temperature, and never gate on
  `run_temp_c`.

Each runs in isolated context, so the athlete name and date MUST be in the prompt text — they are
not inherited.

## 6. Reconcile into ONE concrete recommendation for today

If the two specialists **agree** — recovery clears the training intensity (recovery GO + a quality
session, or both pointing easy) — synthesize directly:

- recovery **GO** → use the training-specialist's prescribed session as-is.
- recovery **EASY** and training already easy → keep it as easy (Z1–Z2).

If the two **genuinely conflict** (e.g. recovery says REST/EASY but training wants tempo/intervals),
invoke the **`conflict-resolver`** subagent. Pass it explicitly: the athlete name, the recovery
call + driving numbers (readiness score/tier, `conflict_detected`, key components, any active
injury/illness), the training prescription + its ACWR band and goal phase, and **any active
`training_directives.intensity_cap`** from the profile (e.g. a `zone2_only` running cap with its
`until` date) so the arbiter applies Rule 1.5 and never up-rates a Z2-capped athlete to intervals
on a running session. It applies the editable priority ladder at
`/Users/tezueshvarshney/work/test/runforlife/runforlife-coach/conflict-rules.md` and returns ONE
decision naming which rule fired. Use that decision as today's call, and name the winning rule in
the rationale below.

Then output exactly this block (numbers first), filling every field:

```
[ATHLETE: <athlete>]  DATE: <date>

Run today: <yes|no>
Type:      <easy|tempo|interval|long|rest>
Distance:  <e.g. 8 km, or "—" if rest>
Pace:      <e.g. 5:40/km, or "—" if rest>
HR zone:   <e.g. Z2, or "—" if rest>

Why: <1-2 lines tying the readiness score/tier and the ACWR band/goal phase to this call.
      If recovery overrode training, name which signal won.>
```

Keep it tight and factual. Do not invent metrics — every number must come from the scripts or the
specialist outputs. If a field is genuinely unavailable from synced data, say so rather than guess.

## 7. Capture feedback when the athlete reacts to prior advice (closes the /reflect loop)

`/reflect` can only learn from recorded feedback. Whenever the athlete tells you how an earlier
recommendation landed — followed it and it worked, ignored it, "that was too hard," felt great,
etc. — record ONE feedback item so the self-evolution loop has fuel. Do this **only on a real
reaction**; never fabricate outcomes to fill the file.

```bash
cd /Users/tezueshvarshney/work/test/runforlife && uv run python runforlife-coach/scripts/memory_manager.py \
  --user <athlete> --add-feedback \
  --advice-type <e.g. deload|tempo|rest_day|long_run> \
  --advice "<the call that was given>" \
  --rating <positive|neutral|negative> \
  [--adherence <followed|partial|ignored>] \
  [--outcome "<what actually happened — metrics if available>"]
```

The record is athlete-scoped (writes `<athlete>/feedback.json`), so it respects the isolation guard.
Keep `advice_type` values consistent across days so `feedback_stats.py` can aggregate them.
