"""
SKILL REGISTRY
===============
Central registry of all available skills.

This is the "toolbox". It does two things:
  1. Tells the LLM what tools exist (get_tool_definitions)
  2. Executes the right tool when the LLM asks for it (execute)

Every agent framework has this concept:
  - LangChain: ToolNode / tool registry
  - CrewAI: tools list
  - OpenAI: functions array
  - Us: SkillRegistry

We're building it from scratch so you see there's no magic.
"""

from runforlife.skills.base import Skill
from runforlife.skills.data.garmin_auth import GarminAuth
from runforlife.skills.data.fetch_activities import FetchActivities
from runforlife.skills.data.fetch_vo2max import FetchVO2Max
from runforlife.skills.data.fetch_sleep import FetchSleep
from runforlife.skills.data.fetch_hrv import FetchHRV
from runforlife.skills.data.fetch_race_predictions import FetchRacePredictions
from runforlife.skills.data.fetch_daily_stats import FetchDailyStats


class SkillRegistry:
    """Holds all skills the agent can use."""

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        self._skills[skill.name] = skill

    def get_tool_definitions(self) -> list[dict]:
        """Get all skill definitions in Anthropic's tool format.

        This list is sent to Claude in the `tools` parameter of every
        API call. Claude reads these to decide which tools to call.
        """
        return [skill.to_tool_definition() for skill in self._skills.values()]

    def execute(self, name: str, arguments: dict) -> dict:
        """Execute a skill by name. Called when Claude returns a tool_use block."""
        skill = self._skills.get(name)
        if not skill:
            return {"error": f"Unknown skill: {name}"}
        try:
            return skill.execute(**arguments)
        except Exception as e:
            return {"error": f"{name} failed: {e}"}


def create_default_registry() -> SkillRegistry:
    """Create a registry with all Phase 1 skills."""
    registry = SkillRegistry()
    registry.register(GarminAuth())
    registry.register(FetchActivities())
    registry.register(FetchVO2Max())
    registry.register(FetchSleep())
    registry.register(FetchHRV())
    registry.register(FetchRacePredictions())
    registry.register(FetchDailyStats())
    return registry
