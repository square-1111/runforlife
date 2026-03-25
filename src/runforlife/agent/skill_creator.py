"""
SKILL-CREATOR AGENT
====================
This is an agent that CREATES skills for other agents.

WHY THIS IS IMPORTANT:
  This is a "meta-agent" — an agent that builds tools for other agents.
  Most agent tutorials stop at "agent uses tools." We're going further:
  "agent CREATES tools."

  This is the foundation for Phase 4 (self-evolving agents). Today we
  trigger it manually. Eventually, the coach agent will call this when
  it realizes it's missing a capability.

HOW IT WORKS:
  1. You give it: an API reference + a skill description (what to build)
  2. It has 3 tools of its own:
     - read_file: read existing skills to learn the pattern
     - write_skill: write a new .py file
     - test_skill: try to import it and catch errors
  3. It loops: write code → test → fix errors → test again → done

  This is the SAME agent loop as the coach agent. The only difference
  is what tools are available and what the system prompt says.
  An agent's behavior is defined by: system prompt + tools.
  Same loop, different personality.

USAGE:
  uv run python -m runforlife.agent.skill_creator

  Then tell it what skill to build, e.g.:
    "Build a fetch_vo2max skill that gets VO2 max data from Garmin Connect"
"""

import json
import subprocess
import sys
from pathlib import Path

from anthropic import Anthropic

# ─── PATHS ──────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
SKILLS_DATA_DIR = PROJECT_ROOT / "src" / "runforlife" / "skills" / "data"
SKILLS_ANALYSIS_DIR = PROJECT_ROOT / "src" / "runforlife" / "skills" / "analysis"

# ─── SYSTEM PROMPT ──────────────────────────────────────────────────
# This defines WHO the agent is and HOW it should behave.
# Compare this to the coach agent's system prompt — same structure,
# completely different purpose.

SYSTEM_PROMPT = """\
You are a Skill Creator agent for the RunForLife project.
Your job is to write Python skill files that follow the project's patterns exactly.

## The Pattern

Every skill MUST:
1. Inherit from `runforlife.skills.base.Skill`
2. Set class attributes: `name`, `description`, `input_schema`
3. Implement `execute(self, **kwargs) -> dict`
4. Import `get_session` from `runforlife.skills.data.garmin_auth` for any Garmin API calls
5. Return human-readable, LLM-friendly data (convert m/s to pace, seconds to H:MM:SS, etc.)
6. Include a pre-computed summary when returning lists (count, totals, averages)
7. Always handle errors gracefully — return {"success": False, "error": "..."} on failure
8. The `user` parameter should always be enum: ["tezuesh", "kakul"]

## Garmin API Reference

The Garmin client object (from `get_session(user)`) has these methods:

### Activities
- `get_activities_by_date(start_date, end_date)` → list of activity dicts
- `get_activity(activity_id)` → single activity detail dict

### Daily Stats
- `get_stats(date_str)` → daily summary (steps, distance, calories, HR, stress)
- `get_stats_and_body(date_str)` → daily stats + body composition combined
- `get_steps_data(date_str)` → detailed step data

### Heart Rate
- `get_heart_rates(date_str)` → {restingHeartRate, maxHeartRate, minHeartRate, heartRateValues: [[timestamp, bpm], ...]}

### VO2 Max & Training
- `get_max_metrics(date_str)` → {generic: {vo2MaxPreciseValue, fitnessAge, ...}}
- `get_training_status(date_str)` → {trainingStatusKey, trainingLoad, ...}
- `get_training_readiness(date_str)` → training readiness score and components
- `get_race_predictions()` → list of {raceDistanceInMeters, raceTimeinSeconds, ...}

### Sleep
- `get_sleep_data(date_str)` → {dailySleepDTO: {sleepTimeSeconds, deepSleepSeconds, lightSleepSeconds, remSleepSeconds, awakeSleepSeconds, sleepScores: {overall: {value, qualifierKey}}}}

### HRV
- `get_hrv_data(date_str)` → {hrvSummary: {lastNightAvg, lastNight5MinHigh, baseline: {lowUpper, balancedLow, balancedUpper}, status, ...}}

### Body Composition
- `get_body_composition(date_str)` → {weight, bmi, bodyFat, muscleMass, ...} (may be empty if no scale)

### Respiration
- `get_respiration_data(date_str)` → breathing rate data

## Rules
- date parameters are always strings in "YYYY-MM-DD" format
- Always use `get_session(user)` — never create a new Garmin() client
- Convert raw Garmin units to human-readable: m/s→pace, seconds→H:MM:SS, meters→km
- Add `"success": True/False` to every return dict
- The description field is CRITICAL — it tells the coach LLM when to use this skill
- Include "Requires garmin_auth to be called first." in every Garmin skill description
- Do NOT add teaching comments — those are in the existing skills already. Write clean production code.
- Do NOT include `if __name__` blocks.

## Workflow
1. First, read existing skills to understand the exact pattern (read_file)
2. Write the skill file (write_skill)
3. Test that it imports correctly (test_skill)
4. If test fails, read the error, fix the code, write again, test again
5. When the skill passes import test, report success
"""

# ─── TOOLS FOR THE SKILL-CREATOR ────────────────────────────────────
# These are the tools THIS agent can use. Notice: same structure as
# the coach agent's skills, but defined inline since they're simple.

TOOLS = [
    {
        "name": "read_file",
        "description": "Read a file from the project. Use this to look at existing skills as examples.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Relative path from project src, e.g. "
                        "'runforlife/skills/data/garmin_auth.py' or "
                        "'runforlife/skills/base.py'"
                    ),
                }
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_skill",
        "description": (
            "Write a new skill file. Provide the filename and full Python source code. "
            "The file will be created in src/runforlife/skills/data/ for data skills "
            "or src/runforlife/skills/analysis/ for analysis skills."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Filename like 'fetch_vo2max.py' or 'goal_tracker.py'",
                },
                "code": {
                    "type": "string",
                    "description": "Full Python source code for the skill",
                },
                "category": {
                    "type": "string",
                    "enum": ["data", "analysis"],
                    "description": "Whether this is a data skill or analysis skill",
                },
            },
            "required": ["filename", "code", "category"],
        },
    },
    {
        "name": "test_skill",
        "description": (
            "Test that a skill file can be imported without errors. "
            "Also verifies the skill class exists and has required attributes. "
            "Returns success or the error message to fix."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "module_path": {
                    "type": "string",
                    "description": "Python import path like 'runforlife.skills.data.fetch_vo2max'",
                }
            },
            "required": ["module_path"],
        },
    },
]


# ─── TOOL IMPLEMENTATIONS ───────────────────────────────────────────

def _execute_read_file(path: str) -> dict:
    full_path = PROJECT_ROOT / "src" / path
    if not full_path.exists():
        return {"success": False, "error": f"File not found: {full_path}"}
    if full_path.is_dir():
        files = [f.name for f in full_path.iterdir() if f.is_file()]
        return {"success": True, "type": "directory", "files": files}
    return {"success": True, "content": full_path.read_text()}


def _execute_write_skill(filename: str, code: str, category: str) -> dict:
    target_dir = SKILLS_DATA_DIR if category == "data" else SKILLS_ANALYSIS_DIR
    file_path = target_dir / filename
    file_path.write_text(code)
    return {
        "success": True,
        "path": str(file_path),
        "message": f"Written {len(code)} bytes to {file_path}",
    }


def _execute_test_skill(module_path: str) -> dict:
    """Run an import test in a subprocess to avoid polluting our own process."""
    test_code = f"""
import sys
sys.path.insert(0, "{PROJECT_ROOT / 'src'}")
try:
    import importlib
    mod = importlib.import_module("{module_path}")
    # Find the Skill subclass
    from runforlife.skills.base import Skill
    skill_classes = [
        v for v in vars(mod).values()
        if isinstance(v, type) and issubclass(v, Skill) and v is not Skill
    ]
    if not skill_classes:
        print("ERROR: No Skill subclass found in module")
        sys.exit(1)
    for cls in skill_classes:
        instance = cls()
        assert instance.name, f"{{cls.__name__}}.name is empty"
        assert instance.description, f"{{cls.__name__}}.description is empty"
        assert instance.input_schema, f"{{cls.__name__}}.input_schema is empty"
        tool_def = instance.to_tool_definition()
        assert "name" in tool_def
        assert "description" in tool_def
        assert "input_schema" in tool_def
        print(f"OK: {{cls.__name__}} (name='{{instance.name}}')")
    print("ALL CHECKS PASSED")
except Exception as e:
    print(f"FAILED: {{e}}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
"""
    result = subprocess.run(
        [sys.executable, "-c", test_code],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode == 0:
        return {"success": True, "output": result.stdout.strip()}
    return {
        "success": False,
        "error": result.stdout.strip() + "\n" + result.stderr.strip(),
    }


TOOL_EXECUTORS = {
    "read_file": _execute_read_file,
    "write_skill": _execute_write_skill,
    "test_skill": _execute_test_skill,
}


# ─── THE AGENT LOOP ─────────────────────────────────────────────────
# Exact same pattern as the coach agent. Same while loop. Same
# stop_reason check. Different system prompt, different tools.
# That's all that distinguishes one agent from another.

def run_skill_creator(task: str) -> str:
    """Run the skill-creator agent with a given task."""
    client = Anthropic()
    messages = [{"role": "user", "content": task}]

    print(f"\n{'='*60}")
    print(f"SKILL CREATOR AGENT")
    print(f"{'='*60}")
    print(f"Task: {task}\n")

    iteration = 0
    while True:
        iteration += 1
        print(f"--- Iteration {iteration} ---")

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8192,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            final_text = "\n".join(
                b.text for b in response.content if b.type == "text"
            )
            print(f"\n{'='*60}")
            print("DONE")
            print(f"{'='*60}\n")
            return final_text

        # Execute tool calls
        tool_results = []
        for block in response.content:
            if block.type == "text":
                print(f"  Thinking: {block.text[:100]}...")
            if block.type != "tool_use":
                continue

            print(f"  >> {block.name}({json.dumps(block.input, default=str)[:80]}...)")

            executor = TOOL_EXECUTORS.get(block.name)
            if not executor:
                result = {"error": f"Unknown tool: {block.name}"}
            else:
                result = executor(**block.input)

            # Print test results
            if block.name == "test_skill":
                status = "PASS" if result.get("success") else "FAIL"
                print(f"  << test: {status}")
                if not result.get("success"):
                    print(f"     {result.get('error', '')[:200]}")

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result, default=str),
            })

        messages.append({"role": "user", "content": tool_results})


# ─── INTERACTIVE MODE ────────────────────────────────────────────────

def main() -> None:
    """Interactive skill creation mode."""
    from dotenv import load_dotenv
    load_dotenv()

    print("Skill Creator Agent")
    print("=" * 40)
    print("Tell me what skill to build.\n")
    print("Examples:")
    print('  "Build fetch_vo2max — gets VO2 max and fitness age from Garmin"')
    print('  "Build fetch_sleep — gets sleep data with stages and score"')
    print('  "Build goal_tracker — tracks 300-day running goal progress"')
    print()

    while True:
        try:
            task = input("Build: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not task:
            continue
        if task.lower() in ("quit", "exit", "q"):
            break

        result = run_skill_creator(task)
        print(result)
        print()


if __name__ == "__main__":
    main()
