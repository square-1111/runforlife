---
name: banister
description: get the athlete's Banister fitness-fatigue-form model state (deterministic)
---

# Banister Fitness-Fatigue-Form Model

Returns the athlete's current Banister model state (Fitness, Fatigue, Form) as
JSON. The numbers are computed **deterministically in Python** from the athlete's
stored training metrics — **never compute or estimate these values by hand.** Run
the command and read the JSON it prints.

## Command

Substitute `<athlete>` with the active athlete name (e.g. `tezuesh` or `kakul`):

```bash
cd /Users/tezueshvarshney/work/test/runforlife && uv run python -m runforlife.rag.banister --user <athlete>
```

The script prints a JSON object and exits. Use the printed values verbatim.

## Output shape

```json
{
  "fitness": 48.2,
  "fatigue": 55.1,
  "tsb": -6.9,
  "trend": "building",
  "overreaching_risk": "moderate",
  "summary": "Fitness (CTL): 48.2 | Fatigue (ATL): 55.1 | Balance (TSB): -6.9 | Trend: Building | Overreaching risk: Moderate"
}
```

If the athlete has fewer than 14 days of stored training data the script returns
no usable state — say so plainly rather than inventing numbers. If the command
errors (e.g. empty DB), report that a `garmin-sync` may be needed instead of
guessing.

## How to interpret it (for coaching)

The model splits training load into three signals:

- **Fitness (CTL — Chronic Training Load):** a 42-day exponentially-weighted
  average of daily load. Rises slowly with consistent training; represents the
  athlete's accumulated aerobic base. Higher is fitter.
- **Fatigue (ATL — Acute Training Load):** a 7-day exponentially-weighted average
  of daily load. Reacts quickly to recent hard sessions. High fatigue means the
  athlete is carrying recent stress.
- **Form (TSB — Training Stress Balance = Fitness − Fatigue):** how fresh the
  athlete is right now.
  - `> +10` — fresh / rested: taper zone, or possibly undertraining.
  - `0 to +10` — optimal racing form.
  - `-10 to 0` — productive fatigue: normal build phase.
  - `< -10` — accumulated fatigue: reduce load.
  - `< -20` — overreaching risk: mandatory recovery.

Also surface `trend` (building / peaking / overreaching / recovering / detraining)
and `overreaching_risk` (low / moderate / high) when advising on whether to push,
hold, or back off. Build fitness by keeping load consistent; peak by letting form
rise into the positive range before a key session or race.
