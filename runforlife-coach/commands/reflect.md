---
description: Weekly self-evolution — mine an athlete's coaching feedback for what's working, then PROPOSE (never auto-apply) edits to conflict-rules.md or specialist prompts, and flag any missing specialist. All changes require explicit user approval.
argument-hint: "[athlete]"
---

# /reflect — propose how the coach should improve

Raw arguments: **$ARGUMENTS**

This is the coach reflecting on its own track record for one athlete. Meant to run roughly
**weekly**. It looks at recorded feedback, finds where advice succeeded or failed, and proposes
concrete, bounded improvements. **You never edit anything without explicit user approval** — this
is opt-in self-evolution, not silent self-modification.

## 1. Resolve the athlete

Parse `$ARGUMENTS` for an athlete token (`tezuesh` or `kakul`, case-sensitive). If none, read the
active pointer:

```bash
cat ~/.runforlife/active_athlete 2>/dev/null
```

If neither yields a valid athlete, **STOP** and reply: `No active athlete set. Run /switch <tezuesh|kakul> first, or pass the name: /reflect tezuesh`.

## 2. Pull the feedback stats (deterministic — do NOT tally yourself)

```bash
cd /Users/tezueshvarshney/work/test/runforlife && uv run python runforlife-coach/scripts/feedback_stats.py --user <athlete>
```

This prints JSON: `{user, total_feedback, advice_types, by_advice_type: {<type>: {n, ratings:{...}, adherence:{...}, sample_outcomes:[...]}}}`.

Also read, for context:
- `~/.runforlife/athletes/<athlete>/insights.json` — patterns already learned.
- `/Users/tezueshvarshney/work/test/runforlife/runforlife-coach/conflict-rules.md` — current ladder.

## 3. Guard against premature conclusions

If `total_feedback` is small (fewer than ~8 entries) or an advice type has `n < 3`, there is **not
enough signal** to change anything. Say so explicitly and stop — do not propose edits off noise.
Report the current stats and what to keep watching. Silent over-fitting to 2 data points is worse
than waiting.

## 4. Find what's working and what isn't

With enough data, for each advice type compare its rating/adherence/outcome mix:
- **Underperforming:** advice types with mostly negative ratings, low adherence, or poor outcomes.
- **Overperforming:** advice the athlete follows and benefits from.
- **Rule mismatches:** cases where a conflict-rule decision (e.g. forcing EASY) repeatedly led the
  athlete to ignore the call with good outcomes, or where a permissive call led to a bad outcome.

Tie every claim to the numbers from step 2. No vibes.

## 5. PROPOSE changes — approval-gated, one at a time

For each well-supported finding, propose ONE concrete change and **ask before applying it**:

- **Conflict-rule tweak:** show the exact current text from `conflict-rules.md` and the proposed
  replacement (a minimal diff), with the evidence. Example: "Rule 3 downgrades tempo→easy in the
  Amber band; `tempo` advice has 5/6 positive outcomes even on Amber days for this athlete —
  propose narrowing Rule 3 to fire only on injury-flagged Amber. Apply this edit? (y/n)"
- **Specialist-prompt tweak:** name the agent file (e.g. `agents/training-specialist.md`), show the
  proposed wording change and why.

Only edit a file after the user says yes. Apply approved edits with a precise, minimal change;
re-show the result. If the user declines, leave the file untouched and note it for next time.

## 6. Skill-gap detection (optional)

Scan `insights.json`, recent `feedback.json`, and the conversation for **recurring questions or
needs no current specialist covers** (e.g. repeated nutrition/fueling or strength-training
questions — the current specialists are recovery / training / race / analytics). If a clear gap
recurs (3+ times), propose adding a new specialist subagent (name + one-line scope) for the user to
approve. Do not create it unprompted.

## 7. Summarize

End with: what the data showed, which edits were applied (with the athlete name), which were
declined or deferred, and what to revisit next week. Keep it concrete and short.
