---
name: readiness
description: Get the athlete's computed daily readiness score (deterministic; do NOT compute it yourself). Use when the athlete asks "how recovered am I?", "am I ready to train?", "what's my readiness today?", or whenever a recovery/training decision needs the composite readiness number. The score, tier, conflict flag, and component breakdown come from a Python script — never from LLM arithmetic.
---

# Readiness

Readiness is a **deterministic, research-validated** composite score (sleep, HRV, ACWR,
subjective wellness, resting HR). It is computed in Python, not by reasoning. Your job is to
**run the script, read its JSON, and interpret the result** — never to recreate or estimate the math.

## The command (run this EXACTLY)

```bash
cd /Users/tezueshvarshney/work/test/runforlife && uv run python -m runforlife.rag.readiness --user <athlete> [--date YYYY-MM-DD]
```

- Replace `<athlete>` with the active athlete name (`tezuesh` or `kakul`). The active athlete is
  set by the SessionStart banner `[ACTIVE: <athlete>]` and `/switch`. Always pass it explicitly.
- `--date YYYY-MM-DD` is optional; omit it for today's readiness.
- The script prints a single JSON object to stdout:

```json
{
  "score": 7.4,
  "tier": "Amber",
  "conflict_detected": false,
  "components": {
    "hrv": 0.82,
    "sleep": 0.71,
    "acwr": 0.65,
    "subjective": 0.50,
    "rhr": 0.60
  }
}
```

Read the values from that JSON. Do not re-derive `score` or `tier` from `components` yourself —
the script already weighted and capped them (including the HRV-vs-subjective conflict rule).

## NEVER do the arithmetic yourself

This is a hard rule:

- **Do NOT** compute, estimate, or "sanity-check" the readiness score by hand.
- **Do NOT** infer the tier from the components — read `tier` straight from the JSON.
- **Do NOT** average, weight, or normalize any metrics in your head.
- If you find yourself adding or multiplying numbers to produce a readiness value, **stop and run
  the script instead.** The Python model is the single source of truth.

You may interpret and explain the JSON (e.g. "your readiness is Amber because subjective wellness
is dragging it down"), but every number you cite must come from the script output.

## Interpreting the result

- `score` — 0–10 composite. Higher is more recovered/ready.
- `tier` — `"Green"` (ready, push), `"Amber"` (proceed with care), `"Red"` (back off / recover).
- `conflict_detected` — `true` when objective signals (e.g. HRV) and subjective wellness
  disagree; surface this explicitly to the athlete and explain which signal the model prioritized.
- `components` — per-signal sub-scores (0–1) for transparency; use them to explain the *why*.

## Caching (avoid repeated cold starts)

`uv run` startup is slow, so **cache the JSON result for the session** and reuse it:

- Run the script **once** per session (or once per requested date) and remember the JSON.
- For any later readiness question in the same conversation, reuse the cached JSON — do **not**
  re-run the script.
- **Only recompute** (re-run the script) after a **fresh Garmin sync** (e.g. after `garmin-sync`
  pulls new data), since new metrics change the underlying inputs. A different `--date` also
  warrants its own run.

## On empty / stale data

If the script reports missing data or errors due to an empty database, do **not** conclude the
athlete has "no training" or fabricate a score. Trigger a sync via the `garmin-sync` skill, then
re-run readiness. Never invent a readiness number to fill the gap.
