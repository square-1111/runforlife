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

# Activity & performance
from runforlife.skills.data.fetch_activities import FetchActivities
from runforlife.skills.data.fetch_activity_detail import FetchActivityDetail
from runforlife.skills.data.fetch_personal_records import FetchPersonalRecords
from runforlife.skills.data.fetch_progress_summary import FetchProgressSummary
from runforlife.skills.data.fetch_race_predictions import FetchRacePredictions

# Fitness & training status
from runforlife.skills.data.fetch_vo2max import FetchVO2Max
from runforlife.skills.data.fetch_endurance_score import FetchEnduranceScore
from runforlife.skills.data.fetch_training_status import FetchTrainingStatus
from runforlife.skills.data.fetch_training_readiness import FetchTrainingReadiness
from runforlife.skills.data.fetch_training_load import FetchTrainingLoad

# Daily recovery & wellness
from runforlife.skills.data.fetch_daily_stats import FetchDailyStats
from runforlife.skills.data.fetch_sleep import FetchSleep
from runforlife.skills.data.fetch_hrv import FetchHRV
from runforlife.skills.data.fetch_body_battery import FetchBodyBattery
from runforlife.skills.data.fetch_stress import FetchStress
from runforlife.skills.data.fetch_heart_rate import FetchHeartRate
from runforlife.skills.data.fetch_spo2_respiration import FetchSpO2Respiration

# Activity & health metrics
from runforlife.skills.data.fetch_steps import FetchSteps
from runforlife.skills.data.fetch_intensity_minutes import FetchIntensityMinutes
from runforlife.skills.data.fetch_weight import FetchWeight

# Gear, goals & planning
from runforlife.skills.data.fetch_gear import FetchGear
from runforlife.skills.data.fetch_goals import FetchGoals
from runforlife.skills.data.fetch_workouts import FetchWorkouts

# Analysis & memory
from runforlife.skills.analysis.remember import Remember
from runforlife.skills.analysis.recall_memory import RecallMemory
from runforlife.skills.analysis.recall_history import RecallHistory
from runforlife.skills.analysis.injury_risk import InjuryRisk
from runforlife.skills.analysis.correlate_metrics import CorrelateMetrics
from runforlife.skills.analysis.weekly_summary import WeeklySummary
from runforlife.skills.analysis.training_trend import TrainingTrend
from runforlife.skills.analysis.z2_pace_trend import Z2PaceTrend
from runforlife.skills.analysis.run_streak import RunStreak
from runforlife.skills.analysis.goal_progress import GoalProgress
from runforlife.skills.analysis.run_sql import RunSQL


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
    """Create a registry with all skills."""
    registry = SkillRegistry()

    # Auth — always register first
    registry.register(GarminAuth())

    # Activity & performance
    registry.register(FetchActivities())
    registry.register(FetchActivityDetail())
    registry.register(FetchPersonalRecords())
    registry.register(FetchProgressSummary())
    registry.register(FetchRacePredictions())

    # Fitness & training status
    registry.register(FetchVO2Max())
    registry.register(FetchEnduranceScore())
    registry.register(FetchTrainingStatus())
    registry.register(FetchTrainingReadiness())
    registry.register(FetchTrainingLoad())

    # Daily recovery & wellness
    registry.register(FetchDailyStats())
    registry.register(FetchSleep())
    registry.register(FetchHRV())
    registry.register(FetchBodyBattery())
    registry.register(FetchStress())
    registry.register(FetchHeartRate())
    registry.register(FetchSpO2Respiration())

    # Activity & health metrics
    registry.register(FetchSteps())
    registry.register(FetchIntensityMinutes())
    registry.register(FetchWeight())

    # Gear, goals & planning
    registry.register(FetchGear())
    registry.register(FetchGoals())
    registry.register(FetchWorkouts())

    # Analysis & memory
    registry.register(Remember())
    registry.register(RecallMemory())
    registry.register(RecallHistory())
    registry.register(InjuryRisk())
    registry.register(CorrelateMetrics())
    registry.register(WeeklySummary())
    registry.register(TrainingTrend())
    registry.register(Z2PaceTrend())
    registry.register(RunStreak())
    registry.register(GoalProgress())
    registry.register(RunSQL())

    return registry
