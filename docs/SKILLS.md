# RunForLife — Skill Registry

Every skill the system will have. We build these incrementally, phase by phase.

Status: `[ ]` = not started, `[~]` = in progress, `[x]` = done

---

## Phase 1 — Foundation (Single Agent + Basic Skills)

> **Learning goal:** Understand what a skill is, how an LLM calls functions, how to structure tool descriptions.

### Data Skills

#### `garmin_auth`
- [ ] **Purpose:** Authenticate with Garmin Connect, manage token refresh
- **Input:** `username`, `password` (first time) or stored tokens
- **Output:** Authenticated session
- **Notes:** Uses `garth` library. Tokens persist to disk. Handles 2FA if enabled.

#### `fetch_activities`
- [ ] **Purpose:** Get list of activities (runs, walks, gym) for a date range
- **Input:** `user` (tezuesh|kakul), `start_date`, `end_date`, `activity_type` (optional)
- **Output:** List of activities with: date, type, distance, duration, avg_pace, avg_hr, calories
- **Notes:** Core skill — almost everything depends on this.

#### `fetch_daily_stats`
- [ ] **Purpose:** Get daily summary (steps, resting HR, stress, body battery)
- **Input:** `user`, `date`
- **Output:** Steps, distance, resting HR, max HR, stress avg, body battery, intensity minutes

#### `fetch_vo2max`
- [ ] **Purpose:** Get current VO2 max estimate
- **Input:** `user`
- **Output:** VO2 max value, trend (improving/maintaining/declining), history

#### `fetch_sleep`
- [ ] **Purpose:** Get sleep data for a date
- **Input:** `user`, `date`
- **Output:** Total sleep, deep/light/REM/awake durations, sleep score, SpO2

#### `fetch_hrv`
- [ ] **Purpose:** Get HRV (heart rate variability) status
- **Input:** `user`, `date`
- **Output:** HRV value, baseline, status (balanced/low/high)

### Analysis Skills

#### `analyze_run`
- [ ] **Purpose:** Break down a single run into useful insights
- **Input:** `activity_id`
- **Output:** Splits, pace chart, HR zones time, cadence, effort level, comparison to similar past runs

#### `goal_tracker`
- [ ] **Purpose:** Track 300-day running goal progress
- **Input:** `user`
- **Output:** Days run so far, target for today's date, deficit/surplus, required pace to hit 300

---

## Phase 2 — Memory + Reflection

> **Learning goal:** How agents persist knowledge, evaluate their own outputs, and improve over time.

### Memory Skills

#### `save_insight`
- [ ] **Purpose:** Store a pattern or learning the agent discovered
- **Input:** `insight_type` (training|recovery|nutrition|lifestyle), `content`, `confidence`
- **Output:** Saved insight with timestamp
- **Example:** "Tezuesh runs slower the day after weed. Avg pace drops 15-20 sec/km."

#### `recall_history`
- [ ] **Purpose:** Retrieve relevant past insights and data
- **Input:** `query` (natural language), `user` (optional)
- **Output:** Relevant past insights ranked by relevance
- **Notes:** This is where we learn about embeddings and vector search.

#### `update_athlete_model`
- [ ] **Purpose:** Maintain a living profile of each athlete's capabilities
- **Input:** `user`, `attribute`, `value`, `evidence`
- **Output:** Updated athlete model
- **Example:** Update Tezuesh's estimated 1km pace from 5:30 to 5:15 based on last 10 runs.

#### `log_feedback`
- [ ] **Purpose:** Record user feedback on agent's advice
- **Input:** `plan_id`, `feedback` (too hard/too easy/just right/didn't follow), `details`
- **Output:** Stored feedback linked to the plan

### Reflection Skills

#### `reflect_on_week`
- [ ] **Purpose:** Agent evaluates what went well and what didn't in the training week
- **Input:** `user`, `week_start`
- **Output:** What was planned vs. actual, adherence %, insights, adjustments for next week
- **Notes:** This is the agent talking to ITSELF — not the user asking. The agent proactively reflects.

#### `evaluate_advice_quality`
- [ ] **Purpose:** Did the agent's past advice lead to good outcomes?
- **Input:** `advice_id`, `outcome_data`
- **Output:** Quality score, what to adjust
- **Notes:** This is meta-cognition — the agent evaluating its own performance.

---

## Phase 3 — Multi-Agent Collaboration

> **Learning goal:** How multiple specialized agents communicate, delegate, and resolve conflicts.

### Planning Skills

#### `daily_plan`
- [ ] **Purpose:** Generate today's training recommendation
- **Input:** `user`, `date`
- **Output:** Run (y/n), type (easy/tempo/interval/long), distance, target pace, HR zone, notes
- **Depends on:** recovery_score, goal_tracker, weekly_plan, recall_history

#### `weekly_plan`
- [ ] **Purpose:** Plan the full training week
- **Input:** `user`, `week_start`, `constraints` (busy days, events, etc.)
- **Output:** 7-day plan with run type, distance, intensity for each day

#### `catchup_plan`
- [ ] **Purpose:** Generate a plan to make up for missed running days
- **Input:** `user`, `deficit_days`, `available_days`
- **Output:** Modified plan that increases frequency without overtraining
- **Notes:** Critical right now — both are 10 days behind.

#### `hyrox_race_strategy`
- [ ] **Purpose:** Generate a pacing and station strategy for an upcoming Hyrox race
- **Input:** `user`, `race_date`, `predicted_fitness`, `partner` (for doubles)
- **Output:** Target 1km splits, station time targets, who does what (doubles), nutrition plan

#### `taper_plan`
- [ ] **Purpose:** Generate the final 1-2 week taper before a race
- **Input:** `user`, `race_date`, `current_training_load`
- **Output:** Reduced volume plan that maintains sharpness

### Inter-Agent Skills

#### `delegate_to_specialist`
- [ ] **Purpose:** Orchestrator routes a sub-task to the right specialist agent
- **Input:** `task_description`, `required_expertise`
- **Output:** Specialist agent's response

#### `resolve_conflict`
- [ ] **Purpose:** When two agents disagree (e.g., coach says run, recovery says rest)
- **Input:** `agent_a_recommendation`, `agent_b_recommendation`, `context`
- **Output:** Resolved recommendation with reasoning

---

## Phase 4 — Self-Evolution

> **Learning goal:** How agents modify their own behavior, create new skills, and optimize their reasoning.

#### `identify_skill_gap`
- [ ] **Purpose:** Agent recognizes it doesn't have a tool for something it needs
- **Input:** `failed_task_description`, `attempted_skills`
- **Output:** Proposed new skill specification

#### `create_skill`
- [ ] **Purpose:** Agent writes code for a new skill
- **Input:** `skill_spec` (name, description, input/output, logic)
- **Output:** New skill code, registered in the system
- **Notes:** This is the "holy grail" — the agent extending itself.

#### `optimize_prompt`
- [ ] **Purpose:** Agent rewrites its own system prompt or skill descriptions based on performance
- **Input:** `current_prompt`, `performance_data`, `feedback`
- **Output:** Improved prompt
- **Notes:** This is prompt evolution — the agent improving how it thinks.

#### `ab_test_strategy`
- [ ] **Purpose:** Agent tries two approaches and measures which works better
- **Input:** `strategy_a`, `strategy_b`, `metric`, `duration`
- **Output:** Winning strategy with confidence score

---

## Skill Implementation Template

When we build each skill, we'll follow this structure:

```python
# skills/data/fetch_activities.py

from typing import Optional
from datetime import date

SKILL_DEFINITION = {
    "name": "fetch_activities",
    "description": "Fetch running and workout activities from Garmin Connect for a specific user and date range. Use this when you need to know what training someone has done.",
    "parameters": {
        "type": "object",
        "properties": {
            "user": {
                "type": "string",
                "enum": ["tezuesh", "kakul"],
                "description": "Which athlete to fetch data for"
            },
            "start_date": {
                "type": "string",
                "description": "Start date in YYYY-MM-DD format"
            },
            "end_date": {
                "type": "string",
                "description": "End date in YYYY-MM-DD format"
            },
            "activity_type": {
                "type": "string",
                "enum": ["running", "walking", "strength", "all"],
                "description": "Filter by activity type. Defaults to 'all'"
            }
        },
        "required": ["user", "start_date", "end_date"]
    }
}

async def execute(user: str, start_date: str, end_date: str, activity_type: str = "all") -> dict:
    """The actual implementation — agent never sees this code."""
    # 1. Get authenticated Garmin session for this user
    # 2. Call Garmin Connect API
    # 3. Filter and format results
    # 4. Return structured data
    pass
```

**Why this structure matters:**
- `SKILL_DEFINITION` is what the LLM sees — it decides whether/how to call the skill based on this
- `execute()` is what actually runs — the LLM only sees its return value
- The description is the most important part — a bad description = the agent picks the wrong skill

---

## Build Order

```
Phase 1 (start here):
  garmin_auth → fetch_activities → fetch_vo2max → analyze_run → goal_tracker
  → fetch_sleep → fetch_hrv → fetch_daily_stats

Phase 2 (after Phase 1 works):
  save_insight → recall_history → log_feedback → reflect_on_week
  → update_athlete_model → evaluate_advice_quality

Phase 3 (after Phase 2 works):
  daily_plan → weekly_plan → catchup_plan → hyrox_race_strategy
  → taper_plan → delegate_to_specialist → resolve_conflict

Phase 4 (after Phase 3 works):
  identify_skill_gap → create_skill → optimize_prompt → ab_test_strategy
```
