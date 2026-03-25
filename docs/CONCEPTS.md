# Agent Concepts — Learning Guide

This document explains agent concepts as we encounter them in this project. It grows as we build.

---

## 1. What is an Agent?

An agent is a program that:
1. **Perceives** — takes input (your question, Garmin data, time of day)
2. **Thinks** — uses an LLM to reason about what to do
3. **Acts** — executes actions using tools/skills
4. **Observes** — looks at the result of its action
5. **Loops** — decides if it needs to do more or if it's done

```
You ask: "How was my running this week?"
        |
        v
   [PERCEIVE] → Agent receives your question
        |
        v
   [THINK]    → LLM reasons: "I need to fetch Garmin data for this week"
        |
        v
   [ACT]      → Calls the `fetch_weekly_runs` skill
        |
        v
   [OBSERVE]  → Gets back: 5 runs, 28km total, avg pace 5:45/km
        |
        v
   [THINK]    → LLM reasons: "Now I can analyze and respond"
        |
        v
   [ACT]      → Generates response with analysis
```

Without skills/tools, an agent is just a chatbot. **Skills are what make an agent an agent.**

---

## 2. What is a Skill (aka Tool)?

A skill is a **function** that an agent can decide to call. It has:

```python
# Every skill has 3 parts:

# 1. A NAME — so the agent can reference it
name = "fetch_weekly_runs"

# 2. A DESCRIPTION — so the LLM knows WHEN to use it
description = "Fetch all running activities for a given week from Garmin Connect"

# 3. A FUNCTION — the actual code that runs
def fetch_weekly_runs(user: str, week_start: str) -> dict:
    # connects to Garmin, pulls data, returns structured result
    ...
```

The LLM reads the name + description to decide which skill to use. It never sees the code inside — it just calls the function and gets a result back.

**Key insight:** The agent doesn't "know" how to talk to Garmin. The skill knows. The agent just knows *when* to use the skill and *what to do* with the result.

---

## 3. Skills vs. Hardcoded Logic

| Approach | Example | Flexibility |
|----------|---------|-------------|
| **Hardcoded** | `if "weekly" in question: fetch_weekly_runs()` | Brittle, breaks on new phrasing |
| **Skill-based** | LLM reads skill descriptions, picks the right one | Handles any phrasing naturally |

This is the fundamental shift: instead of writing `if/else` logic for every scenario, you give the agent a toolbox and let the LLM figure out which tool to grab.

---

## 4. Skill Categories in RunForLife

### Data Skills (fetch & parse)
These connect to external systems and bring data in.

```
┌─────────────────────────────────────────────────┐
│ DATA SKILLS                                      │
├─────────────────────────────────────────────────┤
│ garmin_auth          → Login, manage tokens      │
│ fetch_activities     → Get runs, walks, etc.     │
│ fetch_daily_stats    → Steps, HR, sleep, stress  │
│ fetch_vo2max         → Current VO2 max reading   │
│ fetch_training_load  → Training status/load      │
│ fetch_hrv            → Heart rate variability     │
│ fetch_sleep          → Sleep data & quality       │
│ download_fit_file    → Raw detailed activity data │
│ fetch_hyrox_results  → Past Hyrox race results   │
└─────────────────────────────────────────────────┘
```

### Analysis Skills (compute & derive)
These take raw data and produce insights.

```
┌─────────────────────────────────────────────────┐
│ ANALYSIS SKILLS                                  │
├─────────────────────────────────────────────────┤
│ analyze_run          → Pace, splits, HR zones    │
│ weekly_summary       → Aggregate week's training │
│ trend_analysis       → Progress over weeks/months│
│ vo2max_trend         → VO2 max trajectory        │
│ recovery_score       → Readiness based on HRV,   │
│                        sleep, training load       │
│ goal_tracker         → 300-day goal progress     │
│ hyrox_predictor      → Predict race time based   │
│                        on current fitness         │
│ compare_athletes     → Tezuesh vs Kakul stats    │
└─────────────────────────────────────────────────┘
```

### Planning Skills (decide & prescribe)
These generate recommendations and plans.

```
┌─────────────────────────────────────────────────┐
│ PLANNING SKILLS                                  │
├─────────────────────────────────────────────────┤
│ daily_plan           → What to do today          │
│ weekly_plan          → Plan the week's training  │
│ catchup_plan         → Make up for missed days   │
│ hyrox_race_strategy  → Pacing & station strategy │
│ taper_plan           → Pre-race taper schedule   │
│ recovery_suggestion  → Rest/easy day advice      │
│ adjust_plan          → Modify plan based on how  │
│                        the athlete is feeling     │
└─────────────────────────────────────────────────┘
```

### Memory Skills (remember & learn)
These give the agent persistent knowledge.

```
┌─────────────────────────────────────────────────┐
│ MEMORY SKILLS                                    │
├─────────────────────────────────────────────────┤
│ save_insight         → Store a learned pattern   │
│ recall_history       → What happened last time?  │
│ update_athlete_model → Update beliefs about      │
│                        athlete capabilities       │
│ log_feedback         → "That plan was too hard"  │
│ reflect_on_week      → What worked? What didn't? │
└─────────────────────────────────────────────────┘
```

---

## 5. How Skills Compose (Real Example)

You ask: **"Am I ready for Hyrox next week?"**

The agent's reasoning chain:

```
THINK: I need to assess readiness. Let me gather data.
  ACT:  fetch_activities(last_4_weeks)         → training volume
  ACT:  fetch_vo2max()                         → aerobic fitness
  ACT:  fetch_hrv(today)                       → recovery status
  ACT:  fetch_sleep(last_7_days)               → sleep quality
  ACT:  fetch_hyrox_results(past)              → previous times

THINK: Now let me analyze.
  ACT:  trend_analysis(last_4_weeks)           → fitness trajectory
  ACT:  recovery_score(hrv, sleep, load)       → current readiness
  ACT:  hyrox_predictor(fitness_data)          → estimated race time

THINK: Now let me plan.
  ACT:  taper_plan(days_until_race=7)          → final week plan
  ACT:  hyrox_race_strategy(predicted_time)    → pacing strategy

THINK: I have everything. Let me respond with:
  - Readiness assessment
  - Predicted time range
  - This week's taper plan
  - Race day strategy
```

**This is the power of skills** — the agent orchestrates 10+ function calls to answer one question. You couldn't hardcode this interaction pattern for every possible question.

---

## 6. Self-Evolving Skills (the advanced goal)

This is where it gets interesting. Three levels:

### Level 1: Skill Selection Learning
The agent tracks which skills it uses and which lead to good outcomes.
```
"When the user asks about readiness, fetching HRV data leads to better advice
 than just looking at training volume. Prioritize HRV in readiness assessments."
```

### Level 2: Skill Parameter Tuning
The agent adjusts how it calls skills based on feedback.
```
"Tezuesh said the weekly plan was too aggressive. When generating plans for him,
 reduce intensity by 10% compared to default. Kakul handles the same load fine."
```

### Level 3: Skill Creation
The agent identifies gaps in its toolbox and creates new skills.
```
"I keep getting asked about pace targets for specific HR zones, but I don't have
 a skill for that. Let me create a `hr_zone_pace_calculator` skill."
```

We'll build toward these progressively. Level 1 is Phase 2, Level 2 is Phase 3, Level 3 is Phase 4.

---

## 7. How Skills Relate to Other Agent Concepts

```
┌─────────────────────────────────────────────────────────┐
│                    AGENT ARCHITECTURE                    │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  PERCEPTION ──→ REASONING ──→ ACTION ──→ OBSERVATION   │
│  (input)        (LLM)         (SKILLS)   (results)     │
│                                  │                      │
│                    ┌─────────────┼─────────────┐        │
│                    │             │             │        │
│                 MEMORY      REFLECTION    PLANNING      │
│                 (persist     (evaluate    (multi-step   │
│                  across      quality of   goal          │
│                  sessions)   own output)  pursuit)      │
│                                                         │
│  MULTI-AGENT: Multiple agents, each with own skills,   │
│  collaborating on complex tasks                         │
│                                                         │
│  SELF-EVOLUTION: Agent modifies its own skills,         │
│  memory, and reasoning patterns over time               │
└─────────────────────────────────────────────────────────┘
```

---

*This document will grow as we build each component. Each concept gets a deeper section when we implement it.*
