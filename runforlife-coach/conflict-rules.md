# Conflict Resolution Rules

This is the **editable priority ladder** the `conflict-resolver` subagent applies when two
specialists disagree (the classic case: recovery says REST/EASY, training wants a quality
session). Edit this file in plain text to tune how the coach arbitrates — no code changes
needed. The coach watches outcomes in each athlete's `feedback.json` and these rules can be
adjusted over time.

**The principle:** health and injury-avoidance outrank training stimulus, which outranks the
goal timeline. A missed hard session costs days; an injury costs months. When two signals
collide, the **higher rule on this ladder wins**, and the resolver MUST name which rule fired.

---

## Rule 1 — Acute health override (highest priority)

If ANY of these is active, the decision is **REST** regardless of what training wants:

- An active injury or illness in `ephemeral.json` (entry not expired).
- A sharp HRV downtrend: HRV trending down for **5+ consecutive days** under load.
- Resting HR sustained well above baseline for several mornings (illness / deep fatigue).
- Body battery not recovering overnight combined with poor sleep.

> Fires → **REST** (or active recovery only). Rule 1 beats every rule below it.

## Rule 1.5 — Athlete intensity directive (running cap)

If the athlete's profile carries an **active** `training_directives.intensity_cap`
(`policy: "zone2_only"`, today on or before its `until` date) with
`applies_to: "running"`, the athlete has made an explicit decision that the data
does not get to override:

- **No running session may be up-rated to quality.** A Z2-only cap means every
  RUNNING prescription is held to Z1–Z2 easy/aerobic — tempo, threshold,
  intervals, and strides are **off the table on runs**, even when ACWR, readiness,
  and the goal phase (Rule 4) all say the athlete is ready for them. The arbiter
  may NOT promote a run to intervals/tempo while this cap is in force.
- **Scope is running only.** The cap does NOT touch strength, plyometric, or
  Hyrox-station work — those keep their prescribed intensity. (A strength/Hyrox
  conflict is judged by Rules 1–4 on its own load, not by the running cap.)
- **Self-expiry.** If today is after `until`, the cap has lifted — ignore it and
  arbitrate normally (you may note the cap just expired).
- This rule does NOT force REST and does NOT add load. It only **caps the upper
  intensity of running**. It sits below the acute health override (Rule 1) — an
  active injury still wins — but above the load/goal rules, so a recovered,
  safe-load athlete with a Z2 cap still gets EASY running, never intervals.

> Fires (cap active, conflict is about RUNNING intensity) → the running call is
> held at **EASY (Z1–Z2)** at most; quality running stays off the table. Name the
> trade-off: what the load/goal picture wanted, and when the cap lifts (`until`).

## Rule 2 — High injury-risk load cap

If `ACWR > 1.5` (acute:chronic workload ratio — spiking load, high injury risk):

> Fires → cap at **EASY (Z1–Z2)** at most, and reduce volume. Overrides any goal-driven push
> for intensity. Never prescribe quality work while ACWR is in this band.

## Rule 3 — Caution band

If `ACWR` is between **1.3 and 1.5**, or readiness tier is **Amber** with no Rule-1 trigger:

> Fires → **EASY** only. Hold intensity; keep the athlete moving but unstressed. A training
> request for tempo/intervals is downgraded to easy.

## Rule 4 — Goal-timeline pressure (lowest priority)

Only when Rules 1–3 (and the running-cap in Rule 1.5) do NOT fire (recovery is GREEN, load is in
the safe 0.8–1.3 ACWR band, and no active Z2 running cap):

> The goal timeline and the training plan govern. Use the training-specialist's prescribed
> session as-is (intervals, tempo, long run, etc.). Race deadlines and the 300-day goal are
> honored **only** from a recovered, safe-load base — never by overriding Rules 1, 1.5, 2, or 3.
> In particular, the goal timeline does NOT justify up-rating a run to quality while a Z2 running
> cap (Rule 1.5) is active.

---

## Tie-breaks & defaults

- **When genuinely uncertain, choose the lower-intensity option.** Conservative beats optimistic.
- If recovery and training **agree**, there is no conflict — no need to invoke this resolver.
- `conflict_detected: true` from the readiness script (subjective energy low despite acceptable
  HRV) nudges one step toward caution (treat GREEN as AMBER for the day).

## Output contract (the resolver MUST follow this)

State, in order:
1. **Decision:** REST / EASY / GO (and the concrete session if EASY/GO).
2. **Rule that fired:** e.g. "Rule 2 — ACWR 1.6 > 1.5, high injury-risk load cap."
3. **Why, in 1–2 lines:** tie the winning rule to the actual numbers, and note what the losing
   signal wanted so the athlete sees the trade-off that was made.
