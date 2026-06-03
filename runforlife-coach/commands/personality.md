---
description: Inspect the learned personality model for an athlete (debug) — shows tracked dimensions, signal counts, confidence, and the coaching style block currently in effect
argument-hint: "[athlete]"
---

# /personality — inspect the learned coaching style (debug)

This is a **debug / inspection** command. It does not change anything — it just
reveals what the self-improvement loop has learned about how an athlete likes to
be coached. The model is built up over time by the Stop hook, which extracts
signals from each session and updates `personality.json` (signal-counting,
atomic writes).

The requested athlete is: **$ARGUMENTS**

## 1. Resolve the athlete

- If `$ARGUMENTS` is a non-empty name (e.g. `tezuesh` or `kakul`), use it directly.
- If `$ARGUMENTS` is **empty**, fall back to the active athlete. Read the durable
  pointer at `~/.runforlife/active_athlete` (single line):

  ```bash
  cat ~/.runforlife/active_athlete 2>/dev/null
  ```

  Trim whitespace and use that name. If the pointer is missing or empty, **STOP**
  and reply:

  > No athlete given and no active athlete set. Usage: `/personality [athlete]`,
  > or run `/switch <tezuesh|kakul>` first.

Hold the resolved name as `<athlete>` for the next step.

## 2. Dump the learned model + active style block

Run this from the repo root, substituting the resolved `<athlete>`:

```bash
cd /Users/tezueshvarshney/work/test/runforlife && uv run python -c "import json,sys; from runforlife.storage.personality_store import load_personality, coaching_style_block; u=sys.argv[1]; m=load_personality(u); print(json.dumps(m, indent=2)); print(); print(coaching_style_block(u) or '(no style block yet — confidence < 0.2)')" <athlete>
```

This prints two things:

1. The full `personality.json` model as pretty JSON (including `signal_counts`).
2. The **coaching style block** — the exact text injected into the coach's
   context to shape its tone. If confidence is below `0.2`, no block is emitted
   and you'll see `(no style block yet — confidence < 0.2)` instead.

If the command errors (e.g. the athlete dir doesn't exist), report it plainly
and suggest the athlete may not be initialized yet.

## 3. Interpret the output for the user

After printing the raw output, briefly explain the dimensions so the user can
read the model. Keep it tight:

- **communication** — preferred tone. One of:
  `direct_blunt` (terse, no hand-holding), `balanced` (default), or
  `supportive_narrative` (encouraging, more context and story).
- **data_depth** — how much numeric detail the athlete wants:
  `low` (just the call), `medium` (key metrics), `high` (full splits, HR zones,
  trends, the works).
- **pushback_tolerance** — how hard the coach can challenge them:
  `low` (be gentle, don't argue), `medium`, or `high` (push back hard, debate
  is welcome).
- **plan_style** — how plans should be framed:
  `structured` (explicit prescribed workouts/schedule) or
  `principles_adaptive` (guidelines and principles they adapt themselves).
- **confidence** — `0.0`–`1.0`, computed as `min(1.0, total_signals / 20)`. The
  model is considered fully formed at 20 accumulated signals. **Below `0.2` the
  coach ignores the model entirely** and uses neutral defaults, which is why no
  style block is shown until enough signals are gathered.

Also note for the user:

- A dimension value is only **promoted** away from its default once it has **≥3
  signals AND ≥60%** of that dimension's total signal count — so a single
  offhand session won't flip the model.
- `signal_counts` shows the raw tally per dimension value, so the user can see
  what's driving (or about to drive) each promotion.
- `archetype` and `motivation_driver` may read `unknown` until the loop has
  enough evidence; that's expected for a young model.

Do not invent fields that aren't in the JSON. Present the explanation only for
the dimensions actually shown.
