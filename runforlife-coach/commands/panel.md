---
description: Convene the full expert PANEL on a genuinely cross-domain question — first fetch the numbers ONCE (analytics + parallel-fetch), then fan out five interpretation lenses (run coach, exercise-science, recovery, physio, strength/Hyrox) fed that shared bundle, and synthesize ONE combined numbers-first answer anchored to the sub-60 Hyrox Pro north star. Single-domain/status asks are redirected to the cheaper /pulse or a specialist.
argument-hint: "[athlete] [question...] [--date YYYY-MM-DD]"
---

# /panel — the whole expert panel on one question

Raw arguments: **$ARGUMENTS**

This is for open-ended, **cross-domain** questions where no single specialist owns the answer ("how
should I structure this week?", "is my knee niggle going to derail Hyrox prep?", "am I actually
improving?"). It fetches the numbers ONCE, fans out the interpretation lenses over that shared
bundle, and you synthesize ONE combined call. Follow the steps in order. Numbers first, no LLM
arithmetic — every number comes from a subagent's read of the data, never from you. Single-domain or
status questions are cheaper via `/pulse` or a specific specialist — §5 redirects them.

## 1. Resolve the athlete

Parse `$ARGUMENTS`. It may contain an athlete name, a free-text question, a `--date YYYY-MM-DD`
flag, or any combination (order-independent, but the athlete is the FIRST non-flag word).

1. **If an athlete token is present** (the first non-flag word): it MUST be exactly `tezuesh` or
   `kakul` (case-sensitive). If it is anything else, **STOP** and reply:

   > Invalid athlete `<what they passed>`. Usage: `/panel [tezuesh|kakul] [question...] [--date YYYY-MM-DD]`.

2. **If no athlete token is present**, read the active athlete pointer:

   ```bash
   cat ~/.runforlife/active_athlete 2>/dev/null
   ```

   - If it prints `tezuesh` or `kakul`, use that.
   - If the file is missing or empty, **STOP** and reply:

     > No active athlete set. Run `/switch <tezuesh|kakul>` first, or pass the name: `/panel tezuesh how should I structure this week?`.

3. Hold the resolved name as `<athlete>` for every step below. Always pass it explicitly — never
   let a subagent infer it.

## 2. Parse the question

Everything after the athlete token, with any `--date YYYY-MM-DD` flag removed, is the free-text
`<question>`. Trim whitespace.

- If a `--date YYYY-MM-DD` flag is present, validate it is a real date and hold it as `<date>` to
  pass to the panel; otherwise use today (the current date).
- **If the question is empty** (they passed only an athlete and/or a date), **STOP** and reply:

  > Include a question, e.g. `/panel tezuesh how should I structure this week?`.

Hold the resolved `<question>` for every step below. Always pass it explicitly — subagents run in
isolated context and do NOT inherit it.

## 3. Empty-DB guardrail (carry verbatim — do NOT skip)

If the athlete's metrics DB (`~/.runforlife/athletes/<athlete>/metrics.db`) is missing or has no
rows, the local DB is **unsynced** — this does NOT mean the athlete has not trained or is fully
recovered. **Never** conclude "no training," "no data," or "fully recovered" from an empty DB.
Instead, tell the athlete the data looks unsynced, suggest they run `/garmin-sync` to pull fresh
Garmin data, and STOP — do not fabricate a panel answer. Re-run `/panel` once synced.

## 4. Data freshness — auto-sync the gap before reading (do NOT skip)

Before fanning out, make sure the local DB actually covers up to `<date>` (default today). A stale
DB silently poisons every lens with "as of last week" numbers dressed up as today's.

1. **Read the latest date on file** — the newest `date` in `daily_metrics` for this athlete only:

   ```bash
   sqlite3 ~/.runforlife/athletes/<athlete>/metrics.db \
     "SELECT MAX(date) FROM daily_metrics WHERE user_id='<athlete>';"
   ```

2. **If the latest date is older than yesterday** (there is a gap between it and today),
   **automatically** backfill the gap yourself — do NOT ask the athlete to run a sync by hand. Sync
   from the day after the latest date through today:

   ```bash
   cd "$(cat ~/.runforlife/repo_path)" && uv run python -m runforlife.sync.nightly --user <athlete> --start <day-after-latest> --end <today>
   ```

   This can take a moment — Garmin is rate-limited, so a multi-day range runs for a while.
   Already-ingested days are skipped, so re-running is safe and never double-counts.

3. **If the sync fails** (e.g. `[AUTH FAILED]`, a traceback, or a non-zero exit): fall back to the
   existing behaviour. Do NOT fabricate today's numbers. Tell the athlete the data looks unsynced,
   note it may need a re-auth (`cd "$(cat ~/.runforlife/repo_path)" && uv run python -m
   runforlife.auth <athlete>`), and proceed with an explicit **"as of `<latest date>`"** caveat on
   every figure so nothing pretends to be current.

4. The **empty-DB guardrail (§3) still governs**: if the DB is missing or has zero rows, do not
   sync-then-guess — follow §3 and STOP. Auto-sync only ever *backfills a gap* on a DB that already
   has data; it never manufactures a panel answer from nothing.

## 5. Right-size the fan-out (scale effort to the question — do NOT skip)

The full panel is the heavy path: it spawns multiple subagents and costs ~15× a single read. Only
pay that when the question genuinely spans domains. Classify `<question>` first:

- **Single-domain or status ask** ("how's my sleep?", "what's my ACWR?", "what's he up to?", "am I
  on track for the HM?") — a full panel is wasteful. **STOP** and point the athlete at the cheaper
  route, then do nothing else:

  > That's a `<domain>` question, not a cross-domain one — `/pulse <athlete>` (quick numbers +
  > one next action) or the specific specialist will answer it far cheaper than the full panel.
  > Re-run `/panel` if you want every lens weighing in.

  Map obvious asks: recovery/sleep/HRV → `/status` or recovery-specialist; race/goal/on-track →
  `/goal-status`; "what's he up to"/status/momentum → `/pulse`. If the athlete explicitly says
  "full panel" or "everyone weigh in," treat it as cross-domain and proceed.
- **Genuinely cross-domain** (a call that needs training + recovery + physio + strength to trade
  off against each other — "how should I structure this week?", "is this niggle going to derail
  Hyrox?", "am I overreaching?") — proceed to §6.

## 6. Fetch the numbers ONCE, then fan out thin (do NOT skip)

Do NOT let the lenses each re-query the DB — that is the single biggest source of wasted tokens
(and of inconsistent numbers between lenses). Gather the data ONE time, then hand every lens the
same bundle.

Spawn these **two data-gatherers in parallel** (single message), passing `<athlete>` and `<date>`
explicitly:

- **analytics-specialist** — build the full numeric bundle that §8 needs: the four momentum rows
  (per the "Week-over-week" spec below), runs-done this ISO week, the last ~10-day run log, latest
  ACWR, and weekly km totals. This is the numeric backbone — leave it on its default (capable)
  model.
- **parallel-fetch** — readiness (score/tier + driving components), banister (fitness/fatigue/
  form), and any non-expired ephemeral entries (injury/illness/travel/plan template).

Merge their two returns verbatim into one **DATA BUNDLE** (plain text). Do NOT compute or edit any
number — you only concatenate and label. Carry the §3/§4 guardrails: if the DB was unsynced and
could not be backfilled, mark every figure "as of `<latest date>`"; treat the stale-readiness
placeholder as "no readiness data."

## 7. Fan out the interpretive lenses — thin, tiered, fed the bundle

Invoke these FIVE lenses via the Task tool **in a single message** so they run concurrently. They
are interpretation workers (Haiku) — each runs in isolated context, so the athlete name, the date,
the full `<question>`, **and the entire DATA BUNDLE from §6** MUST be written into every prompt.
Instruct each: **reason over the provided numbers — do NOT re-query the DB or re-run scripts unless
a specific value you need is genuinely missing from the bundle.** Answer ONLY from your lens; if the
question doesn't touch your domain, reply `nothing material to add from my lens` rather than padding.

- **kenyan-camp-coach** — run-execution / training-culture lens: how a top camp would structure the
  running around `<question>` — session sequencing, easy/hard distribution, pacing discipline,
  weekly rhythm.
- **exercise-science-translator** — physiology + evidence lens: the relevant mechanism in plain
  language (aerobic development, adaptation, fueling, fatigue), grounded in the bundle, no jargon.
- **recovery-specialist** — recovery-doctor lens: interpret the readiness/HRV/sleep numbers in the
  bundle — capacity to absorb load, or back off? Restate the readiness score/tier and drivers.
- **physio-specialist** — injury-risk / biomechanics lens: load-management flags (ACWR, volume
  jumps), cadence/over-striding, active niggles; whether the plan raises injury risk.
- **strength-specialist** — Hyrox-guide lens: strength and station implications, and how the running
  plan interacts with strength/compromised-running demands on the road to sub-60.

If a genuine recovery/physio-vs-push conflict emerges, invoke **conflict-resolver** (default model)
per the conflict rule at the end of this file.

## 8. Synthesize ONE combined answer — human, brutal-but-positive, week-over-week

Combine the lenses into a single response written **to the athlete as "you," present tense** — it
answers THEIR question first, not "the panel found X." Do NOT dump separate per-lens blocks. Lens
attributions compress to at most one clause, and only when a lens actually changed the call.

Open with a warm, honest headline, then numbers. Celebrate a real earned win, THEN name the gap.
Show direction of travel (week-over-week), not just a snapshot. Anchor them in the week — "N runs
done, M to go." Close with exactly ONE high-leverage next action. Keep it scannable: a tired
athlete gets the whole verdict from the headline + momentum block in ten seconds.

**Numbers-first, you do NO math.** Every figure — weekly count, km, pace delta, EF, cadence,
runs-left — comes from the analytics-specialist's read of `daily_metrics` (or the `z2_pace_trend`
skill) and the plan template in `ephemeral.json`. You *arrange and translate* numbers; you never
compute, round, or estimate them. Translate jargon (EF, ACWR, TSB) in-line the first time it
appears — never lead with it. If a number is genuinely unavailable from synced data, say so.

Use this structure (adapt wording to voice; fill every `<…>` from a subagent read):

```
# <one warm, honest headline — the answer + the momentum in plain words>
<e.g. "You're behind on stations, but your running engine is genuinely improving — and you're 3 runs into a 6-run week with 3 to go.">

**Where you are this week:** <X> of <N planned> runs done · <M> to go · <this week's km so far> km <optional: "on pace for <projected>"> · readiness <score>/<10> (<tier>)
<if the plan item is expired or missing: "No live plan on file — showing completed work only." and omit the M-to-go figure.>
<if the DB was unsynced and could not be backfilled: honor §3/§4 — either STOP (empty DB) or caveat every figure "as of <latest date>"; never render the blocks below as if current.>

## Momentum — <this week label> vs the last <2–3> weeks
| Metric            | 2 wks ago | last wk | this wk    | trend        |
|-------------------|-----------|---------|------------|--------------|
| Runs / km         | <n>/<km>  | <n>/<km>| <n>/<km>*  | <↑/→/↓ + word> |
| Easy pace (min/km)| <p>       | <p>     | <p>        | <faster/flat/slower by X s/km> |
| EF (pace-at-HR)   | <ef>      | <ef>    | <ef>       | <engine up/flat/down> |
| Cadence (spm)     | <c>       | <c>     | <c>        | <toward/away from target> |
<* this week is partial — km/runs compared through the same weekday as prior weeks.>

**The good news (earned):** <one specific, quantified win — e.g. "your easy pace at the same HR is <X>s/km quicker than <period>: the aerobic base is compounding.">

**The honest bit:** <one specific, quantified limiter — e.g. "<what's behind> is still <number> vs where sub-60 needs it; that's the gap, not your engine.">

## Do this next
<ONE clear, high-leverage action for the next session / rest of the week, autonomy-supportive — e.g. "Your 3 remaining runs: keep Tue quality honest at <target>, hold Sun long easy at <pace> — don't chase km you didn't lose.">
<if a genuine recovery/physio-vs-push conflict fired: state the ONE verdict and name the winning rule — e.g. "Recovery wins this call (Rule 1.5, Z2 cap active) — the quality session stays easy until <date>.">

## Toward sub-60 Hyrox Pro
<honest one-liner tying this week to the north star: does it move you toward it, hold, or cost you, and why — coached without softening.>

<optional single line, only if a lens changed the call: "(<lens>: <the one thing it added>.)">
```

### Week-over-week — how the momentum numbers are built (all from the analytics read)

The trend numbers come from the analytics-specialist's read of `daily_metrics`
(`WHERE user_id='<athlete>'`), never from your own math. Instruct that read to:

- **Weeks:** group runs by ISO week (Mon–Sun). Compare the CURRENT ISO week (Monday 00:00 →
  `<date>`, inclusive) against the previous **2 full ISO weeks** by default (fall back to 1 prior
  week if only one exists; if zero prior weeks of runs exist, say "first week of tracked data — no
  trend yet" and **skip the momentum table** rather than invent one).
- **Partial week:** "this week" is partial. **Never** compare partial-week TOTALS (runs, km) against
  full-week totals — that manufactures a fake regression. For volume, compare
  **cumulative-through-the-same-weekday** (e.g. if `<date>` is Wednesday, compare Mon–Wed this week
  vs Mon–Wed of each prior week) and mark the column `* through <weekday>`. Per-run QUALITY metrics
  (easy pace, EF, cadence, avg HR) use the weekly average as-is — they aren't distorted by an
  incomplete week.
- **Exactly four trend rows** (all from `ran_today=1`):
  1. **Runs / km** — `COUNT(*)` and `ROUND(SUM(run_distance_km),1)` per week (partial week uses
     same-weekday cumulative).
  2. **Easy pace** — `AVG(run_avg_pace_sec_per_km)` over EASY runs only (exclude quality/interval
     days so pace isn't polluted); report as min/km. Lower = faster = improving.
  3. **EF (pace-at-HR proxy)** — `AVG(run_efficiency_factor)`; higher = more distance per heartbeat
     = engine improving. This is the single most important row; if EF is NULL on older rows report
     `n/a` for that week, don't drop the row. Prefer the `z2_pace_trend` skill's EF slope /
     pace-at-ref-HR when available for a like-for-like read.
  4. **Cadence** — `AVG(run_avg_cadence)` spm; frame movement **toward the athlete's target
     cadence** as improvement (per the active cadence-retraining directive), not just up/down.
- **Derived values:** duration = `run_distance_km * run_avg_pace_sec_per_km / 3600` (there is no
  `run_duration` column). **No CTL/ATL/TSB rows** — those live in the separate banister script; do
  not fabricate them here.
- **Phrasing:** state BOTH numbers for any called-out change (`EF <old> → <new>`) and the delta in
  the metric's own unit (`pace -6 s/km`, `cadence +4 spm`) — never a bare percentage or an
  unlabeled arrow. Name at least ONE improvement explicitly every week. Report regression just as
  plainly and specifically (`EF slipped <old>→<new> — two weeks flat now`), framed as a fixable gap,
  never a verdict on the athlete.
- **ACWR is a safety sidecar, not a trend row:** if the latest `acwr` is outside ~0.8–1.3, add one
  caution line; otherwise omit it.

### Runs-left-vs-plan — how "X of N done · M to go" is built

Read the **non-expired** `items[].content` in `~/.runforlife/athletes/<athlete>/ephemeral.json`
(honor `expires_on` — ignore expired items). Parse the free-text weekly template to count the week's
SCHEDULED run sessions (e.g. Tue quality, Wed easy shuffle, Thu easy+strides, Fri brick, Sun long =
the running days; rest/mobility days don't count). `runs_done` = `COUNT(ran_today=1)` for this ISO
week from the analytics read; `runs_left` = `planned_runs − runs_done` (floor at 0). Render as
"X of N planned runs done · M to go." These counts come from the analytics read and the template —
**not** from your own counting. If no non-expired plan item exists, say "no live plan on file —
showing completed work only" and omit the M-to-go figure rather than guessing a schedule.

### Guardrails that survive this rewrite (carry verbatim)

- **No-heat:** never attribute any pace/EF/HR change to temperature, and never gate the comparison
  on `run_temp_c`.
- **Empty-DB / unsynced:** an unsynced or empty DB never means "no training" or "fully recovered" —
  honor §3 and §4. If §4 could not backfill, caveat every figure "as of `<latest date>`"; never
  render the momentum blocks as if they were current.
- **Stale-readiness placeholder:** a readiness of ~5.0 / Amber with every component == 0.5 and all
  additive flags null is the "no data for that day" signature — report it as "no readiness data for
  that day," **not** as a real Amber readiness.

**If the panel produces a genuine conflict** — recovery and/or physio say back off while the
training (kenyan-camp-coach) and/or strength (Hyrox) lenses want to push quality — do NOT split the
difference yourself. Invoke the **`conflict-resolver`** subagent. Pass it explicitly: the athlete
name, the recovery/physio call + driving numbers (readiness score/tier, any active injury/illness),
the training + strength push and their goal-phase rationale, and **any active
`training_directives.intensity_cap`** from the profile (e.g. a `zone2_only` running cap with its
`until` date) so the arbiter applies Rule 1.5 and never up-rates a Z2-capped athlete on a running
session. It applies the editable priority ladder at
`./runforlife-coach/conflict-rules.md` and returns ONE
decision naming which rule fired. Use that decision as the panel's verdict, and name the winning
rule in the answer.

Carry the no-heat rule throughout: never explain pace, EF, HR, or any metric via heat or
temperature, and do not gate the answer on `run_temp_c`.
