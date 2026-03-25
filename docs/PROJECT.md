# RunForLife

A personal running improvement system powered by AI agents — built to get fit AND learn agent architecture.

---

## The People

### Tezuesh Varshney
- Software engineer (sitting job)
- Running for ~6 months, consistent last 3 months
- Past Hyrox: Men's Doubles
- Garmin Forerunner 165
- 300-day individual running goal for 2026

### Kakul Shrivastava
- Software engineer (sitting job)
- Running for ~6 months, consistent last 3 months
- Past Hyrox: Women's Doubles
- Garmin Forerunner 165
- 300-day individual running goal for 2026

### Shared Context
- Weight training 4x/week (1 session is Hyrox station work)
- Prefer 6 days/week running
- Smoke weed once a week
- Dinner by 9 PM, sleep around 1 AM
- Currently ~10 days behind on the 300-day goal — need a catch-up plan

---

## Personal Goals

### 1. Running Improvement
- Build a consistent 6-day/week running habit
- Hit 300 individual running days each in 2026
- Currently behind by ~10 days (as of 2026-03-25) — need to compensate

### 2. VO2 Max Improvement
- Track VO2 max trends via Garmin
- Structure training to push aerobic ceiling (Zone 2 base + interval work)

### 3. Hyrox Performance
- **Next event:** Mixed Doubles, ~early April 2026 (Bangalore/Mumbai area — TBC)
- **Later event:** September 2026 (pan-Asian city — flexible on location)
- First time competing as Mixed Doubles together
- Key focus areas: pacing strategy, sled push/pull, running consistency across 8 rounds

### 4. Hyrox Race Format (reference)
8 rounds of: **1 km run** + **1 workout station**

| Station | Exercise | Mixed Doubles Weights |
|---------|----------|-----------------------|
| 1 | 1000m SkiErg | Alternating |
| 2 | 50m Sled Push | Varies by gender |
| 3 | 50m Sled Pull | Varies by gender |
| 4 | 80m Burpee Broad Jumps | Bodyweight |
| 5 | 1000m Rowing | Alternating |
| 6 | 200m Farmers Carry | Mixed weights |
| 7 | 100m Sandbag Lunges | Mixed weights |
| 8 | 75-100 Wall Balls | Mixed reps/weights |

**Where most people lose time:** Sled push, running rounds 5-8, wall balls (fatigue), burpee broad jumps.

---

## Technical Goals

This project is a **learning vehicle** for AI agent concepts. The running problem is real, but equally important is understanding how to build:

### What We Want to Learn

| Concept | What It Means | How We'll Use It |
|---------|---------------|------------------|
| **Agents** | Autonomous AI programs that perceive, decide, act | Core architecture of the system |
| **Multi-Agent Systems** | Multiple agents collaborating/specializing | Coach agent, data agent, planning agent, etc. |
| **Self-Evolving Agents** | Agents that improve their own behavior over time | Agent reflects on advice quality, adjusts approach |
| **Tool Creation** | Agents that build and use tools | Garmin data fetcher, schedule optimizer, etc. |
| **Memory** | Persistent context across conversations | Training history, preferences, what worked/didn't |
| **Reflection** | Agent evaluates its own outputs and reasoning | Post-run analysis, training plan effectiveness |

### Learning Path (progressive complexity)
1. **Phase 1 — Single Agent + Tools:** One agent that can fetch Garmin data and give basic advice
2. **Phase 2 — Memory + Reflection:** Agent remembers past conversations, reflects on plan effectiveness
3. **Phase 3 — Multi-Agent:** Specialized agents (coach, data analyst, scheduler) that collaborate
4. **Phase 4 — Self-Evolving:** Agents that evaluate and improve their own prompts/strategies

---

## System Architecture (high-level vision)

```
                    +------------------+
                    |   You (Tezuesh   |
                    |   & Kakul)       |
                    +--------+---------+
                             |
                    +--------v---------+
                    |  Orchestrator    |
                    |  Agent           |
                    +--------+---------+
                             |
            +----------------+----------------+
            |                |                |
   +--------v------+ +------v-------+ +------v--------+
   | Data Agent    | | Coach Agent  | | Scheduler     |
   | (Garmin,      | | (Training    | | Agent         |
   |  Hyrox data)  | |  advice,     | | (Weekly plans,|
   |               | |  reflection) | |  catch-up)    |
   +---------------+ +--------------+ +---------------+
            |
   +--------v---------+
   | Tools             |
   | - garminconnect   |
   | - Hyrox scraper   |
   | - Calendar        |
   +-------------------+
```

### Tech Stack
- **Language:** Python
- **Garmin Integration:** `garminconnect` + `garth` (unofficial but best option for personal use)
- **Agent Framework:** TBD — will evaluate LangChain, CrewAI, AutoGen, or build from scratch
- **LLM Provider:** TBD — Anthropic Claude API recommended
- **Data Storage:** TBD — start simple (JSON/SQLite), evolve as needed

### Data Sources
- **Garmin Connect** — activities, VO2 max, HR, sleep, training load, HRV (via `garminconnect` Python library)
- **Hyrox** — past race results, upcoming event info
- **Manual input** — subjective feel, weight training logs, lifestyle factors

---

## Current Status (2026-03-25)

- [ ] Project just kicked off
- [ ] No code written yet
- [ ] Hyrox event in ~2 weeks — immediate need for race strategy
- [ ] 10 days behind on 300-day running goal — need catch-up plan
- [ ] Need to set up Garmin Connect integration first
- [ ] Need to decide on agent framework (or learn by building from scratch)

---

## Open Questions

1. What are Tezuesh and Kakul's current VO2 max numbers? (check Garmin)
2. What were the past Hyrox race times? (Men's Doubles / Women's Doubles)
3. Current average running pace and weekly mileage?
4. Which specific Hyrox events are registered for? (city, date)
5. Agent framework choice — build from scratch for max learning, or use a framework?
6. How to handle the weed/late sleep impact on recovery and training quality?
