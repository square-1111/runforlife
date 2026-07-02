---
description: Convene the full expert PANEL on an athlete's free-text question — spawn all six specialists (elite run coach, exercise-science translator, recovery, physio, strength/Hyrox, analytics) in parallel, each answering from its own lens, then synthesize ONE combined numbers-first answer anchored to the sub-60 Hyrox Pro north star.
argument-hint: "[athlete] [question...] [--date YYYY-MM-DD]"
---

# /panel — the whole expert panel on one question

Raw arguments: **$ARGUMENTS**

This is for open-ended, cross-domain questions where no single specialist owns the answer ("how
should I structure this week?", "is my knee niggle going to derail Hyrox prep?", "am I actually
improving?"). It convenes the FULL panel at once, each member answers from its own lens, and you
synthesize ONE combined call. Follow the steps in order. Numbers first, no LLM arithmetic — every
number comes from a subagent's read of the data, never from you.

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

## 4. Fan out to the panel IN PARALLEL (pass the athlete + question explicitly)

Invoke ALL SIX subagents via the Task tool **in a single message** so they run concurrently — do
not wait for one to finish before starting the next. Each runs in isolated context, so the athlete
name, the target date, and the full question text MUST be written into every prompt — they are not
inherited. In each prompt, state the athlete name and the question explicitly, then ask for that
member's take **from its domain only**. Instruct each agent: answer ONLY from your lens, and if the
question does not touch your domain, reply briefly `nothing material to add from my lens` rather
than reaching outside your expertise or padding.

- **kenyan-camp-coach** — the elite run-execution / training-culture lens: how a top camp would
  structure the running around `<question>` for `<athlete>` — session sequencing, easy/hard
  distribution, pacing discipline, weekly rhythm.
- **exercise-science-translator** — the physiology + evidence lens: explain the relevant mechanism
  in plain language for `<athlete>`'s `<question>` (aerobic development, adaptation, fueling,
  fatigue), grounded in evidence, no jargon.
- **recovery-specialist** — the recovery-doctor lens: sleep / HRV / readiness for `<athlete>` as it
  bears on `<question>` — is there capacity to absorb load, or does the body need to back off?
  Return the readiness score/tier and the driving metrics.
- **physio-specialist** — the injury-risk / biomechanics / rehab lens: any load-management, tissue,
  or movement flags for `<athlete>` relevant to `<question>`; whether the plan raises injury risk.
- **strength-specialist** — the Hyrox-guide lens: strength and Hyrox-station implications of
  `<question>` for `<athlete>` — how the running plan interacts with strength/compromised-running
  demands on the road to sub-60.
- **analytics-specialist** — the data-expert lens: explore `<athlete>`'s `metrics.db` to surface
  the numbers that actually answer `<question>` (trends, volumes, EF/pace-at-HR, ACWR) so the panel
  is grounded in real reads, not guesses.

## 5. Synthesize ONE combined answer

Combine the lenses into a single response — do NOT dump six separate blocks. Structure:

1. **Bottom line (numbers first)** — lead with the concrete answer to `<question>`, anchored to the
   key numbers the analytics and recovery reads returned.
2. **The contributing points** — one tight line per lens that actually added something (skip any
   member that said `nothing material to add from my lens`), attributed to that lens.
3. **North-star anchor** — honestly tie the call to the sub-60 Hyrox Pro north star: does this move
   them toward it, hold, or cost them, and why. Coach the gap without softening.

Every number in the answer must come from a subagent's read — do NOT compute or estimate figures
yourself. If a number is genuinely unavailable from synced data, say so rather than guess.

**If the panel produces a genuine conflict** — recovery and/or physio say back off while the
training (kenyan-camp-coach) and/or strength (Hyrox) lenses want to push quality — do NOT split the
difference yourself. Invoke the **`conflict-resolver`** subagent. Pass it explicitly: the athlete
name, the recovery/physio call + driving numbers (readiness score/tier, any active injury/illness),
the training + strength push and their goal-phase rationale, and **any active
`training_directives.intensity_cap`** from the profile (e.g. a `zone2_only` running cap with its
`until` date) so the arbiter applies Rule 1.5 and never up-rates a Z2-capped athlete on a running
session. It applies the editable priority ladder at
`/Users/tezueshvarshney/work/test/runforlife/runforlife-coach/conflict-rules.md` and returns ONE
decision naming which rule fired. Use that decision as the panel's verdict, and name the winning
rule in the answer.

Carry the no-heat rule throughout: never explain pace, EF, HR, or any metric via heat or
temperature, and do not gate the answer on `run_temp_c`.
