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

Run all three from the repo root. These print JSON / rows — never compute scores yourself.

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

## 4. Empty-DB guardrail (carry verbatim — do NOT skip)

If the readiness or banister scripts error, return no score, or the metrics DB has no rows, the
local DB is **unsynced** — this does NOT mean the athlete has not trained or is fully recovered.
**Never** conclude "no training," "no data," or "fully recovered" from an empty DB. Instead, tell
the athlete the data looks unsynced, suggest they run `/garmin-sync` to pull fresh Garmin data,
and STOP — do not fabricate a plan. Re-run `/daily-plan` once synced.

## 5. Fan out to the specialists (pass the athlete name explicitly)

Invoke BOTH subagents via the Task tool. In each prompt, state the athlete name explicitly and the
target date, and ask for their domain call for today:

- **recovery-specialist** — prompt it to assess `<athlete>` for `<date>` and return its REST /
  EASY / GO call with the readiness score, tier, and the 2-3 driving metrics.
- **training-specialist** — prompt it to assess `<athlete>` for `<date>` and return the next-session
  prescription (type, distance, target pace, HR zone) gated by ACWR band and goal phase.

Run them for the same athlete and date. Each runs in isolated context, so the athlete name and date
MUST be in the prompt text — they are not inherited.

## 6. Synthesize ONE concrete recommendation for today

Reconcile the two specialist outputs into a single call. The recovery call gates intensity; the
training call sets the session shape:

- If recovery says **REST** → today is `Run: no`, type `rest` (or active recovery only).
- If recovery says **EASY** → cap the training prescription at easy (Z1-Z2): keep the distance but
  pin pace/zone to easy, even if training proposed quality.
- If recovery says **GO** → use the training-specialist's prescribed session as-is.
- If the two genuinely conflict (e.g. training wants intervals, recovery says EASY), the
  lower-intensity signal wins — show which signal won and why in the rationale.

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
