---
description: Honest progress check against all of an athlete's goals — sub-HM time, Hyrox date, and the 300-day annual run-days target. Computes pace-to-target deterministically and names the single biggest lever to stay on track.
argument-hint: "[athlete]"
---

# /goal-status — am I on track?

Optional athlete argument: **$ARGUMENTS**

This command gives a blunt, numbers-first status report against the athlete's three goals from
`profile.json`: the sub-X **half marathon** (target time + race date), the **Hyrox** race
(category + partner + date), and the **300-day annual run-days** target. All math is deterministic
(Python via Bash) — you never compute scores or counts in your head.

Follow these steps **in order**.

## 1. Resolve the athlete

- If `$ARGUMENTS` is a non-empty, valid athlete name (`tezuesh` or `kakul`), use it.
- If `$ARGUMENTS` is empty, read the active athlete pointer:

  ```bash
  cat ~/.runforlife/active_athlete 2>/dev/null
  ```

  Use the single name it prints as `<athlete>`.
- If `$ARGUMENTS` is empty AND the pointer is missing/empty, **STOP**. Reply:

  > No active athlete set. Run `/switch <tezuesh|kakul>` first, or pass one: `/goal-status <athlete>`.

- If `$ARGUMENTS` is non-empty but not `tezuesh` or `kakul`, **STOP**. Reply:

  > Invalid athlete `<what they passed>`. Usage: `/goal-status [tezuesh|kakul]`.

Use the resolved name as `<athlete>` everywhere below. Never assume or inherit it.

## 2. Read the goals from the profile (the coach never invents them)

Read `~/.runforlife/athletes/<athlete>/profile.json` with the Read tool. Pull the goals verbatim
from `goals`:

- `half_marathon`: `{target_time, race_date, notes}` — the sub-X HM target.
- `hyrox`: `{category, partner, race_date}` — race category, partner, and date.
- `annual_run_days`: `{target, year}` — e.g. 300 days in 2026.

If `profile.json` is missing, note the athlete is not initialized and suggest running the
init/migration scripts, then **STOP**. The profile is static — READ it, never write it.

## 3. Empty-DB guardrail (check FIRST, before any verdict)

Before computing anything from the metrics DB, confirm there is synced data. Run:

```bash
cd /Users/tezueshvarshney/work/test/runforlife && uv run python3 -c "import sqlite3,pathlib; \
p=pathlib.Path.home()/'.runforlife/athletes/<athlete>/metrics.db'; \
print(0) if not p.exists() else print(sqlite3.connect(str(p)).execute('SELECT COUNT(*) FROM daily_metrics WHERE user_id=?',['<athlete>']).fetchone()[0])"
```

If this prints `0` (or errors), the local DB is **unsynced**. This does NOT mean the athlete hasn't
trained, has zero fitness, or is off track. **Never** conclude "no training," "no data," or "off
track" from an empty DB. Instead tell them the data looks unsynced, suggest `/garmin-sync`, and
**STOP** before giving any goal-gap verdict or run-days count. Re-run `/goal-status` after syncing.

Only continue past this step if the DB has rows.

## 4. Compute the deterministic numbers (Python — never LLM math)

### 4a. Days remaining to each race

```bash
python3 -c "import datetime,json,pathlib; \
p=json.load(open(pathlib.Path.home()/'.runforlife/athletes/<athlete>/profile.json')); \
g=p['goals']; today=datetime.date.today(); \
hm=datetime.date.fromisoformat(g['half_marathon']['race_date']); \
hy=datetime.date.fromisoformat(g['hyrox']['race_date']); \
print(json.dumps({'today':str(today),'hm_days':(hm-today).days,'hm_weeks':round((hm-today).days/7,1),'hyrox_days':(hy-today).days,'hyrox_weeks':round((hy-today).days/7,1)}))"
```

### 4b. 300-day run-days pace (days run this year vs. target-for-today)

Run-days are tracked by the `ran_today` flag in `daily_metrics`. Count distinct dates this year
where `ran_today=1`, then compare against the linear target-for-today (the goal pro-rated to how
far through the year we are).

```bash
cd /Users/tezueshvarshney/work/test/runforlife && uv run python3 -c "import sqlite3,datetime,json,pathlib; \
prof=json.load(open(pathlib.Path.home()/'.runforlife/athletes/<athlete>/profile.json')); \
ard=prof['goals']['annual_run_days']; target=ard['target']; year=ard['year']; \
today=datetime.date.today(); \
days_elapsed=(today-datetime.date(year,1,1)).days+1 if today.year==year else (366 if (year%4==0 and (year%100!=0 or year%400==0)) else 365); \
days_in_year=366 if (year%4==0 and (year%100!=0 or year%400==0)) else 365; \
p=pathlib.Path.home()/'.runforlife/athletes/<athlete>/metrics.db'; \
c=sqlite3.connect(str(p)); \
ran=c.execute('SELECT COUNT(DISTINCT date) FROM daily_metrics WHERE user_id=? AND ran_today=1 AND date>=? AND date<=?',['<athlete>',f'{year}-01-01',f'{year}-12-31']).fetchone()[0]; \
target_today=round(target*days_elapsed/days_in_year,1); \
remaining_days=days_in_year-days_elapsed; \
needed_rate=round((target-ran)/remaining_days,3) if remaining_days>0 else None; \
print(json.dumps({'year':year,'target':target,'days_elapsed':days_elapsed,'days_in_year':days_in_year,'run_days_actual':ran,'target_for_today':target_today,'on_pace_delta':round(ran-target_today,1),'days_left_in_year':remaining_days,'needed_runs_per_day_rest_of_year':needed_rate}))"
```

Interpretation:
- `on_pace_delta` ≥ 0 → ahead of or on the 300-day pace. `< 0` → behind by that many run-days.
- `needed_runs_per_day_rest_of_year` is what the remaining-year cadence must average (≈0.82/day
  ~= 5.7 days/week to hit 300). If it exceeds a sustainable weekly cadence, flag it.

## 5. Get the HM fitness read + prediction — delegate to race-specialist

Do NOT compute fitness or the goal-gap yourself. Invoke the **race-specialist** subagent via the
Task tool, passing the athlete name explicitly and the numbers you already computed. Ask it for:

- the current Banister fitness-fatigue state (CTL / TSB / trend),
- the HM prediction vs. `target_time` and how many minutes off (if any) on the current trajectory,
- the goal HM pace (min/km) and which training phase the athlete should be in given the weeks left,
- a one-line verdict per race goal (HM and Hyrox).

Use the race-specialist's returned numbers and verdict verbatim — do not second-guess its math.
If it reports the DB looks unsynced, defer to the Step 3 guardrail and stop.

## 6. Present the status — crisp table + the single biggest lever

Lead with a tight status table, one row per goal. Numbers first, verdict second. Example shape
(fill with the real computed values — never invent fields):

```
Goal           Target         Now / Pace                 Days left   Status
HM (sub-1:28)  1:28:00 @ ...   <pred> (~N min off)        <hm_days>   On track / N min short
Hyrox (MD)     <category>      base + functional read     <hyrox_days> <verdict>
300-day runs   300 in 2026     <actual> vs <target_today>  <left>     +/-<delta> run-days
```

Then, in one short paragraph, name **the single biggest lever** — the one change that most moves
the athlete toward staying on track across all three goals (e.g. "add one threshold session/week"
or "you're 6 run-days behind pace — bank an easy run on rest days to claw back the 300-day deficit").
Be specific and honest; if a goal is off track, say so in numbers and say what closes the gap. No
filler — only what this athlete's numbers say today.
