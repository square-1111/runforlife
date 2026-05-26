"""
Specialist agent definitions.

Each specialist has:
  - A system prompt persona (built from user profile + memories)
  - A focused tool subset (only the skills relevant to their domain)

The coordinator (coordinator.py) picks which specialist to use per message.
"""

from datetime import date

from runforlife.skills.base import Skill
from runforlife.skills.registry import SkillRegistry


# ── Specialist names (used as keys everywhere) ────────────────────────────
RECOVERY = "recovery"
TRAINING = "training"
RACE = "race"
ANALYTICS = "analytics"

ALL_DOMAINS = (RECOVERY, TRAINING, RACE, ANALYTICS)


# ── System prompt builders ─────────────────────────────────────────────────

def _base_context(user: str) -> str:
    """Load profile + memories and format as shared context block."""
    from runforlife.storage.profile_store import load_profile
    from runforlife.storage.memory_store import load_active_memories

    profile = load_profile(user)
    name = profile["name"]
    goals = profile["goals"]
    ctx = profile["context"]
    hm = goals["half_marathon"]
    hyrox = goals["hyrox"]

    today = date.today()
    race_date = date.fromisoformat(hm["race_date"])
    weeks_remaining = round((race_date - today).days / 7, 1)

    context = f"""\
## Athlete
- Name: {name}
- Watch: {ctx['watch']} | Job: {ctx['job']}
- Sleep: dinner ~{ctx['dinner_time']}, bed ~{ctx['sleep_time']}
- Preferred: {ctx['preferred_run_days_per_week']} run days/week, {ctx['weight_training_sessions_per_week']} weight sessions/week

## Goals
- Half Marathon: sub {hm['target_time']} by {hm['race_date']} ({weeks_remaining} weeks away)
- Hyrox Mixed Doubles: with {hyrox['partner']}, race {hyrox['race_date']}
- Annual run days: {goals['annual_run_days']['target']} in {goals['annual_run_days']['year']}"""

    memories = load_active_memories(user)
    if memories:
        context += "\n\n## What I Know About You\n"
        context += "\n".join(f"- {m}" for m in memories)

    return context


def build_recovery_prompt(user: str) -> str:
    return f"""\
You are a recovery and readiness specialist coach. Your domain: sleep, HRV, \
body battery, stress, injury risk, and training readiness.

Your approach:
- Interpret every metric in context of recent training load — not in isolation
- Distinguish acute fatigue (normal adaptation, 1-2 days) from chronic \
overtraining (danger, 5+ days of declining HRV with high load)
- HRV: one bad night is noise. A 5-day downtrend is a signal.
- Sleep quality matters more than duration for athletic recovery
- When in doubt, recommend recovery — one missed hard session < injury
- Always authenticate with Garmin (garmin_auth) before fetching data
- Use actual numbers, never guess

{_base_context(user)}"""


def build_training_prompt(user: str) -> str:
    return f"""\
You are a training planning and load management coach. Your domain: running \
volume, ACWR, training structure, workouts, gear, and consistency.

Your approach:
- Think in training blocks: base building → build phase → peak → taper
- ACWR safe zone: 0.8–1.3. Above 1.3 = caution. Above 1.5 = high injury risk.
- 80/20 rule: 80% of runs should be easy (Z1–Z2), 20% quality
- Volume before intensity — aerobic base must support the speed work
- Track week-over-week mileage: no more than ~10% increase per week
- We have {(date.fromisoformat('2026-09-28') - date.today()).days // 7} weeks to race — know the phase
- Always authenticate with Garmin (garmin_auth) before fetching data

{_base_context(user)}"""


def build_race_prompt(user: str) -> str:
    from runforlife.storage.profile_store import load_profile
    profile = load_profile(user)
    hm = profile["goals"]["half_marathon"]
    race_date = date.fromisoformat(hm["race_date"])
    weeks_remaining = round((race_date - date.today()).days / 7, 1)

    return f"""\
You are a race performance and strategy coach. Your domain: VO2max, race \
predictions, goal progress, fitness trajectory, and race-day strategy.

Your approach:
- Always anchor analysis to the goal: sub {hm['target_time']} by {hm['race_date']} \
({weeks_remaining} weeks out)
- VO2max is the single best predictor of endurance performance — track it weekly
- Be direct about gaps: if prediction vs goal is 8 minutes, say what needs to change
- Taper: 2–3 weeks of reduced volume before race day
- Race-specific work (threshold, tempo, HM pace): 6–8 weeks before race
- Hyrox: functional strength + SkiErg, sled, burpees — complements running base
- Always authenticate with Garmin (garmin_auth) before fetching data

{_base_context(user)}"""


def build_analytics_prompt(user: str) -> str:
    return f"""\
You are a training data analyst. Your domain: statistical patterns, SQL queries, \
correlations, and custom data exploration.

Your approach:
- Return exact numbers — tables and structured data over prose summaries
- Minimum 30 data points for meaningful correlation; flag when data is thin
- Correlation ≠ causation — always note this when relevant
- When writing SQL: always include WHERE user_id = ? and use ? as placeholder
- Be honest when data is insufficient for conclusions
- Use run_sql for anything not covered by the fixed skills

Table: daily_metrics
Columns: date, hrv_last_night, resting_hr, sleep_score, readiness_score,
  body_battery_end, ran_today (0/1), run_distance_km, run_avg_pace_sec_per_km,
  run_avg_hr, acwr, hrv_7d_slope, sleep_efficiency_delta, rhr_7d_slope

{_base_context(user)}"""


# ── Prompt factory map ─────────────────────────────────────────────────────

PROMPT_BUILDERS = {
    RECOVERY: build_recovery_prompt,
    TRAINING: build_training_prompt,
    RACE: build_race_prompt,
    ANALYTICS: build_analytics_prompt,
}


# ── Specialist registry factories ──────────────────────────────────────────

def _make_registry(skill_classes: list[type[Skill]]) -> SkillRegistry:
    registry = SkillRegistry()
    for cls in skill_classes:
        registry.register(cls())
    return registry


def create_recovery_registry() -> SkillRegistry:
    from runforlife.skills.data.garmin_auth import GarminAuth
    from runforlife.skills.data.fetch_sleep import FetchSleep
    from runforlife.skills.data.fetch_hrv import FetchHRV
    from runforlife.skills.data.fetch_body_battery import FetchBodyBattery
    from runforlife.skills.data.fetch_stress import FetchStress
    from runforlife.skills.data.fetch_heart_rate import FetchHeartRate
    from runforlife.skills.data.fetch_spo2_respiration import FetchSpO2Respiration
    from runforlife.skills.data.fetch_training_readiness import FetchTrainingReadiness
    from runforlife.skills.data.fetch_daily_stats import FetchDailyStats
    from runforlife.skills.analysis.injury_risk import InjuryRisk
    from runforlife.skills.analysis.weekly_summary import WeeklySummary
    from runforlife.skills.analysis.recall_history import RecallHistory
    from runforlife.skills.analysis.remember import Remember
    from runforlife.skills.analysis.recall_memory import RecallMemory

    return _make_registry([
        GarminAuth, FetchSleep, FetchHRV, FetchBodyBattery, FetchStress,
        FetchHeartRate, FetchSpO2Respiration, FetchTrainingReadiness,
        FetchDailyStats, InjuryRisk, WeeklySummary, RecallHistory,
        Remember, RecallMemory,
    ])


def create_training_registry() -> SkillRegistry:
    from runforlife.skills.data.garmin_auth import GarminAuth
    from runforlife.skills.data.fetch_activities import FetchActivities
    from runforlife.skills.data.fetch_activity_detail import FetchActivityDetail
    from runforlife.skills.data.fetch_training_load import FetchTrainingLoad
    from runforlife.skills.data.fetch_training_status import FetchTrainingStatus
    from runforlife.skills.data.fetch_training_readiness import FetchTrainingReadiness
    from runforlife.skills.data.fetch_daily_stats import FetchDailyStats
    from runforlife.skills.data.fetch_workouts import FetchWorkouts
    from runforlife.skills.data.fetch_goals import FetchGoals
    from runforlife.skills.data.fetch_gear import FetchGear
    from runforlife.skills.data.fetch_steps import FetchSteps
    from runforlife.skills.data.fetch_intensity_minutes import FetchIntensityMinutes
    from runforlife.skills.analysis.injury_risk import InjuryRisk
    from runforlife.skills.analysis.weekly_summary import WeeklySummary
    from runforlife.skills.analysis.training_trend import TrainingTrend
    from runforlife.skills.analysis.run_streak import RunStreak
    from runforlife.skills.analysis.goal_progress import GoalProgress
    from runforlife.skills.analysis.recall_history import RecallHistory
    from runforlife.skills.analysis.remember import Remember
    from runforlife.skills.analysis.recall_memory import RecallMemory

    return _make_registry([
        GarminAuth, FetchActivities, FetchActivityDetail, FetchTrainingLoad,
        FetchTrainingStatus, FetchTrainingReadiness, FetchDailyStats,
        FetchWorkouts, FetchGoals, FetchGear, FetchSteps, FetchIntensityMinutes,
        InjuryRisk, WeeklySummary, TrainingTrend, RunStreak, GoalProgress,
        RecallHistory, Remember, RecallMemory,
    ])


def create_race_registry() -> SkillRegistry:
    from runforlife.skills.data.garmin_auth import GarminAuth
    from runforlife.skills.data.fetch_vo2max import FetchVO2Max
    from runforlife.skills.data.fetch_endurance_score import FetchEnduranceScore
    from runforlife.skills.data.fetch_race_predictions import FetchRacePredictions
    from runforlife.skills.data.fetch_personal_records import FetchPersonalRecords
    from runforlife.skills.data.fetch_progress_summary import FetchProgressSummary
    from runforlife.skills.data.fetch_training_status import FetchTrainingStatus
    from runforlife.skills.analysis.goal_progress import GoalProgress
    from runforlife.skills.analysis.training_trend import TrainingTrend
    from runforlife.skills.analysis.weekly_summary import WeeklySummary
    from runforlife.skills.analysis.recall_history import RecallHistory
    from runforlife.skills.analysis.remember import Remember
    from runforlife.skills.analysis.recall_memory import RecallMemory

    return _make_registry([
        GarminAuth, FetchVO2Max, FetchEnduranceScore, FetchRacePredictions,
        FetchPersonalRecords, FetchProgressSummary, FetchTrainingStatus,
        GoalProgress, TrainingTrend, WeeklySummary, RecallHistory,
        Remember, RecallMemory,
    ])


def create_analytics_registry() -> SkillRegistry:
    from runforlife.skills.data.garmin_auth import GarminAuth
    from runforlife.skills.analysis.correlate_metrics import CorrelateMetrics
    from runforlife.skills.analysis.recall_history import RecallHistory
    from runforlife.skills.analysis.run_sql import RunSQL
    from runforlife.skills.analysis.remember import Remember
    from runforlife.skills.analysis.recall_memory import RecallMemory

    return _make_registry([
        GarminAuth, CorrelateMetrics, RecallHistory, RunSQL,
        Remember, RecallMemory,
    ])


REGISTRY_FACTORIES = {
    RECOVERY: create_recovery_registry,
    TRAINING: create_training_registry,
    RACE: create_race_registry,
    ANALYTICS: create_analytics_registry,
}
