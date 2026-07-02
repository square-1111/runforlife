---
description: Side-by-side comparison of both athletes (tezuesh and kakul) on recovery, training, or goals — a read-only snapshot that does NOT change the active athlete.
argument-hint: "[sleep|recovery|training|goals|all]"
---

# /compare — both athletes, side by side

Optional dimension argument: **$ARGUMENTS** (one of `sleep`, `recovery`, `training`, `goals`, `all`;
default `all`).

This answers "how are **both** of us doing?" in one call, instead of the `/switch`-dance. It is
**read-only** and cross-athlete by design — it reads each athlete's `metrics.db` but **never writes**
and **never changes** `active_athlete`. The isolation guard permits cross-athlete *reads*, so this
works without switching. Numbers first.

## 1. Resolve the dimension

Parse `$ARGUMENTS` (case-insensitive). If empty or unrecognized, use `all`. Valid: `sleep`,
`recovery`, `training`, `goals`, `all`.

## 2. Pull a read-only snapshot for BOTH athletes

Do NOT write anything and do NOT touch `~/.runforlife/active_athlete`. Run this read-only query for
**each** athlete (`tezuesh` and `kakul`) — it only SELECTs, so the guard allows it regardless of who
is active:

```bash
cd /Users/tezueshvarshney/work/test/runforlife && for A in tezuesh kakul; do
  echo "=== $A ==="
  uv run python3 -c "
import sqlite3, pathlib, json
p = pathlib.Path.home() / f'.runforlife/athletes/$A/metrics.db'
if not p.exists():
    print(json.dumps({'unsynced': True})); raise SystemExit
c = sqlite3.connect(f'file:{p}?mode=ro', uri=True); c.row_factory = sqlite3.Row
cols = {r[1] for r in c.execute('PRAGMA table_info(daily_metrics)')}
ef = 'ROUND(AVG(run_efficiency_factor),3)' if 'run_efficiency_factor' in cols else 'NULL'
last = c.execute('SELECT * FROM daily_metrics ORDER BY date DESC LIMIT 1').fetchone()
wk = c.execute(f\"SELECT COUNT(*) runs, ROUND(SUM(run_distance_km),1) km, {ef} ef FROM daily_metrics WHERE ran_today=1 AND date>=date('now','-7 days')\").fetchone()
print(json.dumps({'date': last['date'] if last else None, 'sleep_score': last['sleep_score'] if last else None, 'deep': last['deep_sleep_min'] if last else None, 'rem': last['rem_sleep_min'] if last else None, 'rhr': last['resting_hr'] if last else None, 'hrv': last['hrv_last_night'] if last else None, 'runs_7d': wk['runs'], 'km_7d': wk['km'], 'avg_ef_7d': wk['ef']}, default=str))
"
done
```

(The query introspects columns first so it works on an older DB that predates the
`run_efficiency_factor` column — it reports `null` for EF rather than crashing.)

If a DB is missing or empty, note that athlete looks unsynced (suggest `/garmin-sync`) rather than
reporting zeros — do not conclude "not training" from an empty DB.

## 3. For `training` or deeper aerobic comparison — use the z2_pace_trend skill per athlete

When the dimension is `training` (or the user asks "who's improving more?"), also call the
`z2_pace_trend` skill for **each** athlete and compare the EF slope and pace-at-ref-HR.
Compare EF on like-for-like runs (similar distance and intensity). Do NOT attribute EF or
pace-at-HR differences to heat or temperature, and do not gate the comparison on `run_temp_c`.

## 4. For `goals` — read each profile (read-only)

Read `~/.runforlife/athletes/<athlete>/profile.json` for both and compare targets + race dates. Do
not recompute goal-gaps here; point the user to `/goal-status <athlete>` for the per-athlete verdict.

## 5. Present a side-by-side table

Lead with one compact table, one column per athlete, rows for the dimension(s) requested. Example:

```
Metric (last night / 7d)   Tezuesh     Kakul
Sleep score                <…>         <…>
Deep / REM (min)           <…>/<…>     <…>/<…>
RHR / HRV                   <…>/<…>     <…>/<…>
Runs / km (7d)             <…>/<…>     <…>/<…>
Avg EF (7d)                <…>         <…>
```

Then 1–2 lines of contrast — who's fresher, who's building, who needs attention — grounded only in
the numbers above. Keep it tight. Never invent fields not in the data.
