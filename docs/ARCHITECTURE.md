# Architecture — What We Built and Why

This document explains every file, every decision, and the criteria behind each choice.

---

## The Big Picture

We built the **smallest possible working agent** — nothing more.

```
YOU (type a question)
 │
 ▼
AGENT LOOP (agent/core.py)
 │  Sends your question + skill definitions to Claude API
 │  Claude responds with either:
 │    "I need to call a tool" → execute it, send result back, loop
 │    "I have my answer"      → return text to you
 │
 ├── SKILL REGISTRY (skills/registry.py)
 │     Knows what skills exist, can execute them by name
 │
 ├── SKILL: garmin_auth (skills/data/garmin_auth.py)
 │     Logs into Garmin Connect, caches tokens
 │
 └── SKILL: fetch_activities (skills/data/fetch_activities.py)
       Pulls activity data, formats it for the LLM
```

### Project Structure

```
runforlife/
├── pyproject.toml                  ← project manifest (deps, metadata)
├── uv.lock                        ← locked dependency versions
├── .env.example                   ← template for secrets
├── .gitignore                     ← keeps secrets/tokens out of git
├── docs/
│   ├── PROJECT.md                 ← goals, people, context
│   ├── CONCEPTS.md                ← agent concepts learning guide
│   ├── SKILLS.md                  ← skill registry and build plan
│   └── ARCHITECTURE.md            ← this file
├── tokens/                        ← cached Garmin auth tokens (gitignored)
└── src/runforlife/
    ├── __init__.py
    ├── main.py                    ← entry point
    ├── agent/
    │   └── core.py                ← THE AGENT LOOP
    └── skills/
        ├── base.py                ← Skill base class
        ├── registry.py            ← skill toolbox
        ├── data/
        │   ├── garmin_auth.py     ← Skill #1: Garmin authentication
        │   └── fetch_activities.py← Skill #2: fetch activities
        └── analysis/              ← empty, ready for Phase 1 analysis skills
```

---

## File by File — Why Each Exists

### 1. `pyproject.toml` — Project Manifest

**Why it exists:** Every Python project needs one. It tells `uv` what dependencies to install, what Python version to use, and how to build the package.

**Why these specific dependencies:**

| Dependency | Why |
|---|---|
| `anthropic` | The Claude API client — the agent's "brain" |
| `garminconnect` + `garth` | Talk to Garmin. `garth` handles SSO auth, `garminconnect` wraps the data API |
| `python-dotenv` | Load `.env` file so we don't hardcode secrets in code |
| `pydantic` | Structured data validation — will be used more in Phase 2 |

**Why `uv` over pip/poetry/pipenv:**
- 10-100x faster than pip
- Has a lockfile (`uv.lock`) for reproducible installs
- Manages Python versions
- Created by the Astral team (same people who built `ruff`)
- The 2025-2026 standard for Python project management

**Why `src/` layout:**
Prevents a subtle Python bug. Without `src/`, when you run `python` from the project root, `import runforlife` might import from the local directory instead of the installed package. The `src/` folder forces Python to use the properly installed version. This is the default in `uv init --lib` and is considered best practice.

**Why `dependency-groups` for dev deps (not `optional-dependencies`):**
`dependency-groups` (PEP 735) is the modern way to declare dev/test dependencies. `optional-dependencies` is for features users can opt into (like `pip install runforlife[postgres]`). Dev tools aren't user-facing features.

---

### 2. `skills/base.py` — The Skill Contract

```python
class Skill(ABC):
    name: str          # What the LLM calls it
    description: str   # How the LLM decides WHEN to use it
    input_schema: dict # What parameters the LLM can pass

    def execute(self, **kwargs) -> dict: ...       # The actual code
    def to_tool_definition(self) -> dict: ...      # Convert to Anthropic format
```

**Why it exists:**
Without it, each skill would invent its own format. One might call it `"parameters"`, another `"input_schema"`, another might forget the description. The base class says: "every skill MUST have these three things."

**Why abstract base class (ABC):**
If you create a skill and forget to implement `execute()`, Python throws an error at class creation time — not at runtime when a user is waiting. Fail fast, fail loud.

**Why `to_tool_definition()`:**
Anthropic's API expects tools in a specific JSON format:
```json
{
    "name": "skill_name",
    "description": "what it does and when to use it",
    "input_schema": { "type": "object", "properties": {...} }
}
```
This method converts our skill to that format. The alternative — hand-building this dict in every skill — is repetitive and error-prone.

**Design criteria:** Thinnest useful abstraction. Just enough structure to prevent mistakes. If it only saves you from one type of bug, it's worth it. If it adds complexity without preventing bugs, delete it.

---

### 3. `skills/data/garmin_auth.py` — Skill #1: Authentication

**Why this is skill #1:**
Everything else depends on being logged into Garmin. Without auth, no data. Without data, no agent. This must exist before anything else.

**Key design decisions:**

#### Token caching (`tokens/` directory)
Garmin rate-limits logins and can throw CAPTCHAs. Logging in every time the agent starts would break constantly. So we:
1. First try: load saved tokens from disk (fast, no network)
2. Fallback: fresh login with username/password
3. Always: save tokens after successful auth

#### Session cache (`_sessions` dict)
Other skills need the authenticated Garmin session object. Instead of re-authenticating inside every skill, `garmin_auth` stores the session in memory and other skills grab it via `get_session(user)`.

This is internal plumbing — the LLM doesn't know about it.

#### What the LLM sees vs. what the code does

The LLM only sees this:
```json
{
    "name": "garmin_auth",
    "description": "Authenticate with Garmin Connect for a specific user...",
    "input_schema": {
        "properties": {
            "user": { "enum": ["tezuesh", "kakul"] }
        }
    }
}
```

It doesn't know about tokens, sessions, caching, or the `garth` library. It just knows: "call this first, pass a user name, get back success/failure."

**That's the skill abstraction — hide the plumbing, expose the intent.**

---

### 4. `skills/data/fetch_activities.py` — Skill #2: Activity Data

**Why this is skill #2:**
Activities are the core data. Runs, walks, gym sessions — everything the coach needs to reason about training load, progress, and goals.

**Key design decisions:**

#### `_parse_activity()` — Data transformation

Garmin returns ~100 fields per activity with cryptic names and raw units:
```python
# What Garmin returns:
{"averageSpeed": 3.017, "duration": 1832.4, "distance": 5234.7}

# What we transform it to:
{"avg_pace": "5:32/km", "duration": "30:32", "distance_km": 5.23}
```

**Why transform?** The LLM reads the return value. `"5:32/km"` is something it can put in a sentence and reason about. `3.017 m/s` is not. The LLM would have to do math to convert it, and LLMs are bad at math.

**Rule: Do math in code, do reasoning in the LLM.**

#### Pre-computed summary

```python
return {
    "activity_count": 12,       # LLM doesn't have to count the list
    "run_count": 8,             # LLM doesn't have to filter + count
    "total_distance_km": 47.3,  # LLM doesn't have to sum
    "total_duration": "6:12:30",# LLM doesn't have to add durations
    "activities": [...]         # Raw data still available if needed
}
```

**Why?** LLMs are unreliable at arithmetic. If you return 30 activities and ask "how many km total?", the LLM might miscount or misadd. Pre-computing the summary means the LLM can just reference the number.

#### `ACTIVITY_TYPE_MAP`

Garmin calls treadmill running `"treadmill_running"` and outdoor running `"running"`. When the LLM says `activity_type: "running"`, we want both. The map handles that translation so the LLM doesn't need to know Garmin's internal type system.

---

### 5. `skills/registry.py` — The Toolbox

```python
class SkillRegistry:
    def register(skill)            # Add a skill to the toolbox
    def get_tool_definitions()     # Get all skills in Anthropic's format
    def execute(name, arguments)   # Run a skill by name
```

**Why it exists:**
The agent needs two capabilities:
1. A list of all tools to send to Claude (so Claude knows what's available)
2. A way to execute a tool when Claude asks for one

The registry provides both. Without it, the agent would have hardcoded references to every skill.

**Why `create_default_registry()`:**
A factory function that sets up all Phase 1 skills. When we add new skills, we add one line here:
```python
registry.register(NewSkill())
```
The agent code doesn't change. This is the Open-Closed Principle in action — open for extension (new skills), closed for modification (agent loop doesn't change).

**This is the same pattern everywhere:**
- LangChain calls it a "tool registry"
- CrewAI calls it a "tools list"
- OpenAI calls it a "functions array"
- We call it `SkillRegistry`

Same concept, different names.

---

### 6. `agent/core.py` — THE AGENT LOOP

**This is the most important file in the entire project.** Everything else exists to support it.

```python
def chat(self, user_message: str) -> str:
    # 1. Add user message to conversation history
    # 2. while True:
    #      Call Claude with history + tool definitions
    #      if stop_reason == "end_turn":  → return the text response
    #      if stop_reason == "tool_use":  → execute tools, add results, loop
```

#### Why it's a while loop

The agent might need multiple tool calls to answer one question:

```
You: "How was my running this week?"

  Loop iteration 1:
    Claude returns: tool_use → garmin_auth(user="tezuesh")
    We execute it, send result back

  Loop iteration 2:
    Claude returns: tool_use → fetch_activities(user="tezuesh", ...)
    We execute it, send result back

  Loop iteration 3:
    Claude returns: end_turn → "You ran 4 times this week for 28km..."
    We return the text. Loop ends.
```

The loop runs until Claude says "I'm done" (`stop_reason == "end_turn"`).

#### Why we keep conversation history

Claude's API is stateless — every API call starts from scratch. If we don't send the full conversation, Claude won't remember what was said 2 messages ago.

`self.conversation` (a list of message dicts) IS the agent's short-term memory. It grows with every exchange. (In Phase 2, we'll add long-term memory that persists across sessions.)

#### Why we send tool definitions on EVERY call

Claude needs to know what tools are available each time. There's no "register tools once" endpoint in Anthropic's API. We send the full list with every request.

This might seem wasteful, but it's by design — it means you can dynamically change the available tools between calls. (In Phase 4, the self-evolving agent will use this to add new skills at runtime.)

#### Why `system` prompt is separate from `messages`

Anthropic's API separates:
- **System prompt** → agent's identity, rules, constraints (persistent frame)
- **Messages** → the actual conversation (user messages, assistant responses, tool results)

The system prompt is read first and sets the context for everything else. It's not a "message" — it's the agent's DNA.

#### The `stop_reason` decision point

```python
if response.stop_reason == "end_turn":
    # Claude decided it has enough info to respond
    return the text

# Otherwise: stop_reason == "tool_use"
# Claude decided it needs more information
# Execute tools, send results back, let Claude decide again
```

**This is the "agent" part.** The LLM decides what to do — not our code. We don't have if/else logic saying "if the user asks about running, call fetch_activities." Claude reads the skill descriptions and figures it out.

---

### 7. `main.py` — Entry Point

Simple input/output loop. Nothing architecturally interesting. It:
1. Loads `.env` (secrets)
2. Creates the registry (toolbox with all skills)
3. Creates the agent (gives it the toolbox)
4. Loops: read input → `agent.chat()` → print response

Run with: `uv run python -m runforlife.main`

---

## Design Criteria Summary

Every decision was made against these criteria:

| Criteria | What it means | Example |
|---|---|---|
| **Simplest thing that works** | Don't add complexity before you need it | No frameworks, no classes where functions suffice |
| **Fail fast, fail loud** | Errors should surface immediately, not silently | ABC for skills, explicit error returns |
| **Do math in code, reasoning in LLM** | LLMs are bad at arithmetic, good at language | Pre-computed summaries, human-readable pace |
| **Hide plumbing, expose intent** | Skills hide implementation, expose what the LLM needs | LLM sees "authenticate" not "load tokens from disk" |
| **Thinnest useful abstraction** | Just enough structure to prevent mistakes | Skill base class has 3 fields and 2 methods, nothing more |
| **Open for extension** | Adding skills shouldn't require changing the agent | Registry pattern, `create_default_registry()` |

---

## What We Deliberately Don't Have Yet

| Not built | Why not yet | When |
|---|---|---|
| Memory / persistence | Get the core loop working first. The agent forgets everything between sessions right now — that's fine for Phase 1. | Phase 2 |
| Multiple agents | One agent is enough to learn the core pattern. | Phase 3 |
| Streaming responses | Nice UX but not essential for learning. | Later |
| Error retries | Premature. Let it fail loudly so we see what breaks. | When we see patterns in failures |
| Tests | Mostly API wiring right now. We'll add tests when there's logic worth testing. | When analysis skills arrive |
| Structured output validation | Pydantic models for tool outputs. Not needed until outputs get complex. | Phase 2 |

---

## The One Insight

**An agent = a while loop that lets the LLM decide what happens next.**

Every framework, every "agentic AI" product, every multi-agent system — at the bottom of the stack, there's this loop:

```
while True:
    response = call_llm(messages, tools)
    if response.done:
        return response.text
    else:
        result = execute_tool(response.tool_call)
        messages.append(result)
```

We built it in ~100 lines. Everything from here is layers on top.

---

## The Skill-Creator Agent (`agent/skill_creator.py`)

This is the second agent in our system, and it teaches a critical concept:
**agents can build tools for other agents.**

### What It Is

A "meta-agent" — an agent whose job is to write Python code for new skills.
Instead of us manually writing `fetch_vo2max.py`, `fetch_sleep.py`, etc.,
we tell this agent what to build and it:

1. Reads existing skills to learn the pattern
2. Writes the new skill file
3. Tests it (tries to import it)
4. Fixes errors and retries if the test fails
5. Reports success

### Why This Matters

```
LEVEL 1 (most tutorials):  Human writes tools → Agent uses tools
LEVEL 2 (what we built):   Agent writes tools → Other agent uses tools
LEVEL 3 (Phase 4 goal):    Agent realizes it needs a tool → creates it → uses it
```

We're at Level 2. The jump to Level 3 is "just" adding the self-awareness
for the coach agent to notice skill gaps.

### Architecture Insight: Same Loop, Different Personality

Compare the two agents:

| | Coach Agent (`agent/core.py`) | Skill Creator (`agent/skill_creator.py`) |
|---|---|---|
| **System prompt** | "You are a running coach..." | "You are a skill creator..." |
| **Tools** | garmin_auth, fetch_activities, ... | read_file, write_skill, test_skill |
| **Loop** | Same while loop | Same while loop |
| **stop_reason check** | Same | Same |

**The agent loop is identical.** The only things that differ are:
1. The system prompt (who am I, what do I do)
2. The tools (what can I do)

This is the most important insight about agents: **system prompt + tools = behavior.**
The loop is just plumbing.

### Its Three Tools

#### `read_file`
- **Purpose:** Read existing skill files to learn the pattern
- **Why it needs this:** Without seeing real examples, the LLM would guess at the
  project's coding style. With examples, it matches exactly.

#### `write_skill`
- **Purpose:** Write a new `.py` file in the skills directory
- **Why it needs this:** The agent can't create files without a tool to do so.
  This is a "code generation" tool — the simplest form of self-modification.

#### `test_skill`
- **Purpose:** Try to import the skill and verify it has the right structure
- **Why it needs this:** This is the **feedback loop**. Without it, the agent
  writes code and hopes it works. With it, the agent writes code, tests it,
  sees errors, and fixes them. This test→fix loop is what makes it an agent
  rather than a one-shot code generator.
- **How it works:** Runs a subprocess that imports the module and checks:
  - Does the module import without errors?
  - Does it contain a Skill subclass?
  - Does the class have name, description, input_schema?
  - Does to_tool_definition() return the right format?

### The Agent's Workflow (what actually happens)

```
You: "Build fetch_vo2max"

  Iteration 1:
    Agent thinks: "Let me look at an existing skill for the pattern"
    → read_file("runforlife/skills/data/fetch_activities.py")
    ← gets the code

  Iteration 2:
    Agent thinks: "Now I understand the pattern. Let me write the skill"
    → write_skill("fetch_vo2max.py", <code>, "data")
    ← file written

  Iteration 3:
    Agent thinks: "Let me test if it imports"
    → test_skill("runforlife.skills.data.fetch_vo2max")
    ← FAIL: "NameError: name 'Any' is not defined"

  Iteration 4:
    Agent thinks: "I forgot to import Any from typing. Let me fix it"
    → write_skill("fetch_vo2max.py", <fixed code>, "data")
    ← file written

  Iteration 5:
    → test_skill("runforlife.skills.data.fetch_vo2max")
    ← PASS: "OK: FetchVO2Max (name='fetch_vo2max')"

  Agent: "Done! Created fetch_vo2max skill at skills/data/fetch_vo2max.py"
```

The test→fix loop is iterations 3-5. That's the "agentic" part — it
doesn't just generate code, it **verifies and iterates**.

### How to Use It

```bash
# Interactive mode
uv run python -m runforlife.agent.skill_creator

# Or programmatically
from runforlife.agent.skill_creator import run_skill_creator
result = run_skill_creator("Build a fetch_sleep skill that gets sleep data from Garmin")
```

### What to Build With It

These are the remaining Phase 1 skills from SKILLS.md:

| Skill | What to tell the agent |
|---|---|
| `fetch_vo2max` | "Build fetch_vo2max — gets VO2 max, fitness age, training status, and load from Garmin" |
| `fetch_sleep` | "Build fetch_sleep — gets sleep data with stages (deep/light/REM), duration, and sleep score" |
| `fetch_hrv` | "Build fetch_hrv — gets HRV summary with last night average, baseline, and status" |
| `fetch_daily_stats` | "Build fetch_daily_stats — gets daily summary: steps, resting HR, stress, body battery, calories" |
| `fetch_race_predictions` | "Build fetch_race_predictions — gets Garmin's predicted race times for 5K, 10K, half, full marathon" |
| `goal_tracker` | "Build goal_tracker — tracks 300-day running goal. Takes activities data and calculates days run, deficit, required pace to hit 300" |

After each one is created, register it in `skills/registry.py` and the coach agent can use it immediately.
