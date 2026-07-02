---
description: Build a safe, goal-aligned 7-day running plan for an athlete — progressing load within ACWR 0.8-1.3, with at least one rest/easy day, anchored to their banister form/fatigue, recent volume, profile goals, and any active travel/injury constraints.
argument-hint: "[athlete] [--start YYYY-MM-DD]"
---

# /weekly-plan — build a 7-day running plan

Arguments received: **$ARGUMENTS**

This is a genuinely **cross-domain** request: it needs training-load math (volume,
ACWR, intensity split), fitness-fatigue state (banister), and goal alignment
(race phase, taper). Delegate to the specialist subagents — do not freehand the
sports science yourself, and never do arithmetic in your head (all numbers come
from the Python scripts the specialists run).

Follow these steps **in order**.

## 1. Resolve the athlete

Parse `$ARGUMENTS`:

- The **athlete** is the first bare token (not starting with `--`), if present. It
  must be exactly `tezuesh` or `kakul` (case-sensitive). If a bare token is present
  but is anything else, **STOP** and reply:

  > Invalid athlete `<what they passed>`. Usage: `/weekly-plan [tezuesh|kakul] [--start YYYY-MM-DD]`.

- If **no** athlete token was passed, fall back to the active athlete. Read it with
  Bash so `~` expands:

  ```bash
  cat ~/.runforlife/active_athlete 2>/dev/null
  ```

  - If that prints a valid name (`tezuesh` or `kakul`), use it and say which
    athlete you resolved (e.g. "Using active athlete: tezuesh").
  - If the file is missing or empty, **STOP**. Do not guess. Reply:

    > No active athlete set. Run `/switch <tezuesh|kakul>` first, or pass the athlete: `/weekly-plan <tezuesh|kakul>`.

Use the resolved name as `<athlete>` everywhere below. Never let it be empty.

## 2. Resolve the start date

- If `$ARGUMENTS` contains `--start YYYY-MM-DD`, validate it is a real ISO date.
  If it is malformed, **STOP** and reply with the usage line from step 1.
- If `--start` is absent, the plan starts **tomorrow** (today is a coaching/planning
  day, not a training day you can still influence retroactively). Compute it
  deterministically — do not eyeball the calendar:

  ```bash
  python3 -c "import datetime; print((datetime.date.today()+datetime.timedelta(days=1)).isoformat())"
  ```

  Label the 7 days `Day 1 … Day 7` with their explicit calendar dates (and weekday
  names) so the athlete can drop them into a real week.

## 3. Pull the goal + active constraints (read directly)

Read these for `<athlete>` so the plan is anchored, not generic:

- **Profile / goals** (static — coach reads, never writes):
  `~/.runforlife/athletes/<athlete>/profile.json`
  - `goals.half_marathon` → `{target_time, race_date}` (the sub-X HM target → race phase).
  - `goals.hyrox` → `{category, partner, race_date}` (Hyrox needs running base + strength).
  - `goals.annual_run_days` → `{target, year}` (the 300-day consistency anchor — run-days/week matters).
  - `preferences` → preferred run days/week, long-run day, etc., if present.
- **Active ephemeral constraints** (travel / injury / life — only non-expired items):
  `~/.runforlife/athletes/<athlete>/ephemeral.json`
  - Travel days → schedule easy/rest or treadmill-friendly sessions, not key workouts.
  - **Injury / niggle → demote intensity and volume on affected days; when in doubt,
    rest. Safety wins over progression.**
  - **Active interval-block template → the scheduled plan to build against.** Among
    the non-expired `items[].content`, find the interval-block template (free text,
    e.g. `"INTERVAL BLOCK ... Weekly template: Mon rest+mobility | Tue QUALITY | Wed
    leg day+easy shuffle | Thu push/pull+easy+strides | Fri brick | Sat rest/easy |
    Sun long run easy. Quality alternates short(400-800m)/long(1.2-2km). 4-wk split:
    W1 6x400@17.5 ... Long run W1-4: 14/16/17/13km. Easy 11.2-11.6km/h."`). Extract
    from it: the **day-by-day weekly structure**, **which week of the 4-week split**
    the athlete is in and its **reps/paces**, and the **long-run progression**. This
    is the DEFAULT shape the 7-day plan must follow (§5) — not a generic 80/20 week.
    Only honor non-expired items; if no such template is on file, fall back to the
    generic 80/20 week.

- **Completed sessions this week** (metrics.db — coach reads, never writes): read what
  the athlete has ALREADY done in the current calendar week (Mon → today) so the plan
  covers only the REMAINING days and never double-books a session already run:

  ```bash
  cd /Users/tezueshvarshney/work/test/runforlife && uv run python -c "
  import sqlite3, datetime, os
  a='<athlete>'
  db=os.path.expanduser(f'~/.runforlife/athletes/{a}/metrics.db')
  today=datetime.date.today(); monday=today-datetime.timedelta(days=today.weekday())
  con=sqlite3.connect(db)
  for r in con.execute('SELECT date, ran_today, run_distance_km, run_avg_pace_sec_per_km, run_avg_hr, run_avg_cadence, run_efficiency_factor FROM daily_metrics WHERE user_id=? AND date>=? AND date<=? ORDER BY date', (a, monday.isoformat(), today.isoformat())):
      print(r)
  "
  ```

  From these rows, note **which days this week already have a run**, and whether this
  week's **quality session** and **long run** are already done (a long run reads as a
  clearly larger `run_distance_km`; a quality session as a faster
  `run_avg_pace_sec_per_km`). You are only reading which sessions exist — do NOT do
  arithmetic yourself; the training-specialist still owns all volume/ACWR math. Feed
  this into §5 so the generated plan fills only the REMAINING days.

If `profile.json` is missing, the athlete is not initialized — say so and suggest
running the init/migration scripts; do not fabricate goals.

## 4. Delegate to the specialists (cross-domain fan-out)

### Auto-sync freshness check (run BEFORE the fan-out)

The plan must be built on **fresh volume/ACWR**, so bring the DB current first. Find the
latest ingested date:

```bash
cd /Users/tezueshvarshney/work/test/runforlife && uv run python -c "
import sqlite3, os
a='<athlete>'
db=os.path.expanduser(f'~/.runforlife/athletes/{a}/metrics.db')
row=sqlite3.connect(db).execute('SELECT max(date) FROM daily_metrics WHERE user_id=?', (a,)).fetchone()
print(row[0] if row and row[0] else 'NONE')
"
```

Let `latest` be that value and `yesterday` = today − 1 day. Then:

- **If `latest` is `NONE`** (empty DB): run `uv run python -m runforlife.sync.nightly
  --user <athlete>` to pull at least yesterday; if the DB is still empty afterward, go
  straight to the §6 empty-DB guardrail.
- **If `latest` is older than `yesterday`:** sync the gap automatically — from the day
  AFTER `latest` through today:

  ```bash
  cd /Users/tezueshvarshney/work/test/runforlife && uv run python -m runforlife.sync.nightly --user <athlete> --start <day-after-latest> --end <today>
  ```

  Compute `<day-after-latest>` deterministically, e.g. `python3 -c "import datetime;
  print((datetime.date.fromisoformat('<latest>')+datetime.timedelta(days=1)).isoformat())"`.
  Garmin is rate-limited, so a multi-day range can take a few minutes — let it finish.
  Re-running is safe (already-ingested days are skipped).
- **If `latest` is already yesterday or today:** the DB is fresh — skip the sync.

**On sync failure** (the command errors, or the DB is still stale afterward), do NOT
block the plan. Fall back to the §6 empty-DB guardrail and build the week off the data
you have, adding an explicit **"as of `<latest date>`"** caveat so the athlete knows the
plan is anchored to the last synced day, not today.

### Fan-out

Invoke the specialist subagents via the **Task tool**, passing `<athlete>` and the
`--start` date **explicitly** in each prompt (they run in isolated context and never
inherit the athlete name).

1. **training-specialist** — ask for: current weekly volume (week-over-week), the
   **current ACWR and which band it sits in**, the intensity split as real counts
   (easy vs quality), recent run-day consistency vs the 300-day target, and the
   banister fitness/fatigue/TSB read. Tell it you are building a 7-day plan and need
   the load picture plus a safe weekly volume target.
2. **race-specialist** — ask for: the race phase given weeks-to-race (base → build →
   peak → taper), HM goal pace and the training paces around it, and whether this
   week should carry race-specific quality work or is a taper/recovery week. Pass the
   HM and Hyrox `race_date`s so it can compute weeks remaining.

3. **strength-specialist** (call this ONLY when the athlete has a Hyrox goal in
   `goals.hyrox`, or the week should carry strength/cross-training) — ask for: the
   non-running session counts over the last 4 weeks by type, the Hyrox station
   benchmarks vs targets (it will say plainly when none are on file — do not invent
   them), and the next strength/station session to slot into the week. Pass the
   Hyrox `race_date` so it can phase the station work. If there is no Hyrox goal,
   skip it.

If only consistency/base-building is in question and there is no near race, the
race-specialist may be light — but still call it to confirm the phase. Pass the
**active ephemeral constraints** from step 3 into every prompt so none prescribes
a hard session on a travel/injury day. Fan the specialists out **in parallel** —
issue the Task calls in a single message so they run concurrently.

## 5. Build the 7-day plan (synthesize, within the safety rails)

Combine the specialists' numbers into one concrete week. Honor these rules:

- **Progress load safely — ACWR stays in the 0.8–1.3 band.** Use the
  training-specialist's current weekly volume as the base. If ACWR is already in
  caution (1.3–1.5) or high-risk (>1.5), this week **holds or reduces volume** — no
  ramp. If under 0.8 (undertrained), ramp gradually. The week-over-week volume
  ceiling is **~10%**; do not exceed it.
- **At least one full rest day** (more if banister TSB is deep-negative / overreaching
  or readiness is low). At least one **easy** day beyond that.
- **80/20 intensity** — most of the week easy (Z1–Z2), at most ~20% quality (tempo /
  threshold / intervals), and only if the race phase and ACWR allow it. Volume before
  intensity.
- **One long run**, placed on the athlete's preferred long-run day if known.
- **Align to the goal phase** from the race-specialist (race-specific paces only in
  build/peak; easy aerobic + consistency in base; reduced volume in taper).
- **Match the athlete's scheduled interval-block template (§3) by default.** The
  day-by-day shape, the current week's reps/paces, and the long-run progression come
  from THEIR template — not a generic 80/20 week. Where the template and the safety
  rails (ACWR 0.8–1.3, ≥1 rest day, ~10% ceiling) conflict, **safety still wins** —
  demote, shorten, or move the session — but the default weekly shape follows the
  scheduled block. If no template is on file, build the generic 80/20 week above.
- **Cover only the REMAINING days; never double-book what's already banked (§3).** For
  plan days that fall in the current calendar week, skip days that already have a run,
  and if this week's quality session or long run is already done, do NOT prescribe
  another one — fill the rest of the week around what the athlete has already
  completed.
- **Slot the strength/Hyrox work** from the strength-specialist (when it ran) onto
  the right days — keep heavy lower-body/station work off hard-run days, and label
  it in the plan (the "Run type" column may read `strength` or `Hyrox stations`).
  If the strength-specialist reported no station benchmarks on file, carry that note
  through — do not fabricate station targets.
- **Respect active constraints** — travel days are easy/treadmill/rest; injury days
  are rest or cross-train, never quality.

For **each of the 7 days** give exactly:

| Day | Date (weekday) | Run type | Distance | Intensity / HR zone | Target pace |
|-----|----------------|----------|----------|---------------------|-------------|

- **Run type:** rest / easy / long / recovery / tempo / threshold / intervals / cross-train.
- **Distance** in km (`0 / rest` for rest days).
- **Intensity / zone:** the HR zone (e.g. Z2) or "rest".
- **Target pace** where applicable (e.g. "5:40/km"), from the race-specialist's paces.

Then add a short summary line: planned weekly volume vs current, the resulting ACWR
direction (climbing toward / holding within the safe band), run-days this week vs the
300-day target, and the one-sentence rationale tied to the race phase. Be specific —
never "add some tempo work." Say which day, distance, pace, zone.

## 6. Empty-DB guardrail (carry verbatim)

If the specialists report that their scripts errored, returned no data, or the metrics
DB has no rows, the local DB is **unsynced** — this does NOT mean the athlete hasn't
trained or has zero mileage/fitness. **Never** conclude "zero training," "no data," or
build a plan off an assumed zero base. Instead, tell the athlete the data looks unsynced,
suggest they run `/garmin-sync` to pull fresh Garmin data, and re-run `/weekly-plan`.
You may offer a conservative base-maintenance week (mostly easy, with rest days) as a
stopgap, but flag clearly that it is unanchored until the data syncs.

## 7. Close

End with the `[ACTIVE: <athlete>]` line and a one-line offer to adjust the plan
(swap a day, shift the long run, scale volume) so the athlete can iterate.
