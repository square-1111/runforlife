---
description: Render multi-week trend charts (RHR, HRV, sleep, volume, Efficiency Factor) for an athlete as inline ASCII sparklines — a read-only snapshot that does NOT change the active athlete.
argument-hint: "[athlete] [weeks]"
---

# /chart — trend sparklines for an athlete

Optional arguments: **$ARGUMENTS** — an athlete name (`tezuesh` or `kakul`) and/or a week count
(default 4). This is **read-only**: it reads the athlete's `metrics.db` but never writes and never
changes `active_athlete`. The isolation guard permits cross-athlete *reads*, so you can chart either
athlete without switching.

## 1. Resolve athlete + window

Parse `$ARGUMENTS`. Athlete: the first `tezuesh`/`kakul` token, else the active athlete
(`cat ~/.runforlife/active_athlete`). Weeks: the first integer, else `4`. If no valid athlete, STOP
and ask them to pass one or `/switch` first.

## 2. Pull the series (read-only) and render with the sparkline helper

Run this — it reads the last N weeks read-only and prints a sparkline row per metric. The series come
straight from `daily_metrics`; the rendering uses the project's `render_row` helper so it's consistent:

```bash
cd "$(cat ~/.runforlife/repo_path)" && uv run python3 -c "
import sqlite3, pathlib, sys
sys.path.insert(0, 'src')
from runforlife.skills.analysis.sparkline import render_row
A = '<athlete>'; weeks = <weeks>
p = pathlib.Path.home() / f'.runforlife/athletes/{A}/metrics.db'
if not p.exists():
    print(f'{A}: unsynced — run /garmin-sync'); raise SystemExit
c = sqlite3.connect(f'file:{p}?mode=ro', uri=True); c.row_factory = sqlite3.Row
rows = list(c.execute(
    \"SELECT date, resting_hr, hrv_last_night, sleep_score, run_distance_km, run_efficiency_factor \"
    \"FROM daily_metrics WHERE date >= date('now', ?) ORDER BY date\", (f'-{weeks*7} days',)))
def col(k): return [r[k] for r in rows]
print(f'{A} — last {weeks} weeks ({len(rows)} days)')
print(render_row('RHR',      col('resting_hr'), 'bpm'))
print(render_row('HRV',      col('hrv_last_night'), 'ms'))
print(render_row('Sleep',    col('sleep_score')))
print(render_row('Run km',   col('run_distance_km'), 'km'))
print(render_row('EF',       col('run_efficiency_factor')))
"
```

(Substitute `<athlete>` and `<weeks>`. The query is read-only — `mode=ro` — and column-safe via the
fixed SELECT list. EF is null on pre-EF rows; the helper shows `(no data)` rather than crashing.)

## 3. For training-load trend, use the banister history if asked

If the user specifically wants CTL/TSB over time, pull the banister series (it reads the same DB) and
render those too; otherwise the five wellness/run metrics above are the default.

## 4. Present

Show the sparkline block as-is (monospace), then 1–2 lines reading the trend — which way RHR/HRV are
moving, whether volume is building, whether EF (aerobic efficiency) is rising. Numbers/arrows come
from the helper; do not invent values. To compare both athletes, run the block for each and place the
two blocks side by side (this is the `/compare`-style read).
