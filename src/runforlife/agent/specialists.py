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


def _format_metrics_table(rows: list[dict]) -> str:
    """
    Compact fixed-width table of daily metrics, oldest → newest.

    Columns chosen to give the coach instant pattern awareness:
    HRV trend, sleep quality, readiness, training load, and run distance.
    """
    if not rows:
        return "  (no data yet — run nightly sync to populate)"

    header = "  date         hrv  rhr  sleep  ready  batt   km    acwr  hrv_slope"
    sep    = "  " + "-" * 66
    lines  = [header, sep]

    for r in rows:
        def v(key, fmt="{}", fallback="—"):
            val = r.get(key)
            return fmt.format(val) if val is not None else fallback

        hrv   = v("hrv_last_night",       "{:.0f}")
        rhr   = v("resting_hr",           "{}")
        sleep = v("sleep_score",          "{}")
        ready = v("readiness_score",      "{}")
        batt  = v("body_battery_end",     "{}")
        km    = v("run_distance_km",      "{:.1f}") if r.get("ran_today") else "—"
        acwr  = v("acwr",                 "{:.2f}")
        slope = v("hrv_7d_slope",         "{:+.1f}")

        lines.append(
            f"  {r['date']}  {hrv:>4} {rhr:>4} {sleep:>5} {ready:>5} {batt:>4} "
            f"{km:>5}  {acwr:>5}  {slope:>9}"
        )

    return "\n".join(lines)


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

    from runforlife.storage.metrics_store import get_recent
    recent = list(reversed(get_recent(user, n=14)))  # oldest → newest
    context += f"\n\n## Recent 14 Days\n{_format_metrics_table(recent)}"

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
- If recall_history returns no rows, the local DB is unsynced — NOT that the athlete hasn't trained. \
Always fall back to live Garmin: fetch_activities, fetch_training_load, fetch_training_status
- Never conclude "zero training" from an empty DB. Confirm with live data first.

Before responding, reason through the data deeply:
- Fetch fetch_hr_zones first so all HR analysis uses real zone boundaries.
- Go through EVERY activity from fetch_activities one by one. Count session types. \
  Compute actual percentages. Don't estimate — calculate.
- Ask yourself: what is this athlete actually training? What are they missing? \
  What does the pattern tell me about their trajectory toward the goal?
- Only write the response after you've done that analysis in your thinking.

Tool usage — use the right tool for the job:
- For per-workout analysis (what training has been done, intensity, session types): \
  call fetch_activities(user, start_date, end_date, activity_type="all"). \
  Returns each session: type, distance, avg_pace, avg_hr, max_hr, training_effect_aerobic, \
  training_effect_anaerobic. Use this whenever the athlete asks about their training.
- For zone compliance on a specific run: call fetch_activity_detail(user, activity_id) \
  which returns hr_zones with % time in each zone.
- For the athlete's zone boundaries: call fetch_hr_zones(user).
- For HRV trends, ACWR, weekly aggregates over a longer window: use recall_history.
- Always compute start_date from today minus the requested window.

Coaching output rules — follow these strictly:
- Classify every session using actual avg_hr and zone boundaries: \
  easy (avg_hr in Z1-Z2), moderate (avg_hr in Z3), hard (avg_hr in Z4-Z5).
- Diagnose the intensity split with real counts: "38 easy runs, 0 threshold, 8 cycling."
- That diagnosis IS the coaching insight — not the volume number.
- Prescription = specific day, specific workout, specific pace, specific distance. \
  Never say "add tempo work." Say "Tuesday: 2km warmup + 5km at 4:50/km + 1km cooldown."
- Volume without intensity context is meaningless — always report both.

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
- If recall_history returns no rows, the local DB is unsynced — NOT that the athlete hasn't trained. \
Always fall back to live Garmin: fetch_vo2max, fetch_race_predictions, goal_progress, fetch_training_status
- Never conclude "zero training" or "no data" from an empty DB. Live tools always have current data.

Before responding, reason through the data deeply:
- Fetch fetch_hr_zones first so all HR analysis uses real zone boundaries, not guesses.
- Go through every activity from fetch_activities. Compute real intensity split percentages. \
  Look at pace progression over weeks. Check if long runs are getting faster or stagnating.
- Connect training pattern to the goal gap. Explain the mechanism, not just the gap number.
- Only write the response after you've done that analysis in your thinking.

Tool usage — use the right tool for the job:
- For per-workout analysis (pace per run, HR per run, speed sessions, cycling sessions): \
  call fetch_activities(user, start_date, end_date, activity_type="all"). \
  This returns each individual workout with avg_pace, avg_hr, max_hr, training_effect_aerobic, \
  training_effect_anaerobic, distance_km, type. Use this for any "last N weeks of training" question.
- For zone compliance on a specific run: call fetch_activity_detail(user, activity_id).
- For the athlete's zone boundaries: call fetch_hr_zones(user).
- For aggregate trends (HRV slope, ACWR, weekly totals over months): use recall_history.
- For goal gap and race prediction: use goal_progress or fetch_race_predictions.
- Always compute start_date from today's date minus the requested window.

Coaching output rules — follow these strictly:
- Look at EVERY activity returned by fetch_activities. Identify: easy runs (avg_hr < 150, \
  pace > 5:30/km), threshold runs (avg_hr 160-170), intervals (max_hr > 175), \
  cycling (type contains "cycling"), strength work.
- Identify what training is MISSING: no speed sessions? No threshold work? Only easy pace?
- Structure: (1) what the data shows — be specific about sessions, \
  (2) root cause diagnosis of any gap, (3) specific prescription.
- Use real numbers from the data. "Your last 5 long runs averaged 5:42/km at 148bpm" \
  not "your pace is slow."
- Never give generic advice. Prescription = specific workout, specific pace, specific day.
- Pace conversion: speed in m/s → pace in min/km = 1000 ÷ speed ÷ 60.

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
    from runforlife.skills.data.fetch_hr_zones import FetchHRZones
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
        GarminAuth, FetchActivities, FetchActivityDetail, FetchHRZones,
        FetchTrainingLoad, FetchTrainingStatus, FetchTrainingReadiness, FetchDailyStats,
        FetchWorkouts, FetchGoals, FetchGear, FetchSteps, FetchIntensityMinutes,
        InjuryRisk, WeeklySummary, TrainingTrend, RunStreak, GoalProgress,
        RecallHistory, Remember, RecallMemory,
    ])


def create_race_registry() -> SkillRegistry:
    from runforlife.skills.data.garmin_auth import GarminAuth
    from runforlife.skills.data.fetch_hr_zones import FetchHRZones
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
        GarminAuth, FetchHRZones, FetchVO2Max, FetchEnduranceScore, FetchRacePredictions,
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
