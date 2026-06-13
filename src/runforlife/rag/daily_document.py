"""
DailyDocument: one row per athlete per day.

Fields are stored directly in SQLite (metrics_store.py) — no vector
embedding. All queries are SQL: window functions, threshold filters,
and aggregates work on exact numeric values.
"""

from dataclasses import dataclass


@dataclass
class DailyDocument:
    user: str
    date: str  # YYYY-MM-DD

    # --- Sleep ---
    sleep_duration_min: float | None = None
    sleep_score: int | None = None
    sleep_efficiency: float | None = None   # 0-100 %
    deep_sleep_min: int | None = None       # minutes in deep sleep
    rem_sleep_min: int | None = None        # minutes in REM
    light_sleep_min: int | None = None      # minutes in light sleep
    sleep_start_local: str | None = None    # bedtime e.g. "23:45"
    sleep_hr_avg: int | None = None         # avg HR during sleep
    respiration_avg: float | None = None    # avg breaths/min during sleep

    # --- HRV ---
    hrv_last_night: float | None = None     # ms — nightly average
    hrv_weekly_avg: int | None = None       # ms — Garmin 7-day average
    hrv_5min_high: int | None = None        # ms — peak 5-min reading
    hrv_baseline_low: int | None = None     # ms — Garmin personal baseline low
    hrv_baseline_high: int | None = None    # ms — Garmin personal baseline high
    hrv_garmin_status: str | None = None    # "BALANCED" | "UNBALANCED" | "LOW"

    # --- Heart Rate ---
    resting_hr: int | None = None           # bpm

    # --- Recovery & Readiness ---
    readiness_score: int | None = None      # 0-100 (Garmin training readiness)
    body_battery_morning: int | None = None # 0-100 at wake time
    body_battery_peak: int | None = None    # 0-100 daily peak
    body_battery_end: int | None = None     # 0-100 most recent
    stress_avg: int | None = None           # 0-100 daily average
    stress_max: int | None = None           # 0-100 daily peak
    stress_qualifier: str | None = None     # "CALM" | "BALANCED" | "STRESSFUL" etc.

    # --- Activity ---
    steps: int | None = None
    active_calories: int | None = None

    # --- Running ---
    ran_today: bool = False
    run_distance_km: float | None = None
    run_avg_pace_sec_per_km: float | None = None
    run_avg_hr: int | None = None
    training_effect_aerobic: float | None = None
    run_is_indoor: bool | None = None       # True = treadmill/indoor (pace not heat-confounded)
    run_temp_c: float | None = None          # avg ambient temp °C during the run (heat normalization)

    # --- Fitness ---
    vo2_max: float | None = None            # ml/kg/min — Garmin estimate

    # --- Computed features (populated by features.py during ingestion) ---
    acwr: float | None = None               # Acute:Chronic Workload Ratio
    hrv_7d_slope: float | None = None       # ms/day (negative = declining)
    sleep_efficiency_delta: float | None = None  # vs 28d baseline (pp)
    rhr_7d_slope: float | None = None       # bpm/day over 7d

    def to_row(self) -> dict:
        """Flat dict for SQLite INSERT OR REPLACE."""
        return {
            "user_id":                  self.user,
            "date":                     self.date,
            "sleep_duration_min":       self.sleep_duration_min,
            "sleep_score":              self.sleep_score,
            "sleep_efficiency":         self.sleep_efficiency,
            "deep_sleep_min":           self.deep_sleep_min,
            "rem_sleep_min":            self.rem_sleep_min,
            "light_sleep_min":          self.light_sleep_min,
            "sleep_start_local":        self.sleep_start_local,
            "sleep_hr_avg":             self.sleep_hr_avg,
            "respiration_avg":          self.respiration_avg,
            "hrv_last_night":           self.hrv_last_night,
            "hrv_weekly_avg":           self.hrv_weekly_avg,
            "hrv_5min_high":            self.hrv_5min_high,
            "hrv_baseline_low":         self.hrv_baseline_low,
            "hrv_baseline_high":        self.hrv_baseline_high,
            "hrv_garmin_status":        self.hrv_garmin_status,
            "resting_hr":               self.resting_hr,
            "readiness_score":          self.readiness_score,
            "body_battery_morning":     self.body_battery_morning,
            "body_battery_peak":        self.body_battery_peak,
            "body_battery_end":         self.body_battery_end,
            "stress_avg":               self.stress_avg,
            "stress_max":               self.stress_max,
            "stress_qualifier":         self.stress_qualifier,
            "steps":                    self.steps,
            "active_calories":          self.active_calories,
            "ran_today":                int(self.ran_today),
            "run_distance_km":          self.run_distance_km,
            "run_avg_pace_sec_per_km":  self.run_avg_pace_sec_per_km,
            "run_avg_hr":               self.run_avg_hr,
            "training_effect_aerobic":  self.training_effect_aerobic,
            "run_is_indoor":            None if self.run_is_indoor is None else int(self.run_is_indoor),
            "run_temp_c":               self.run_temp_c,
            "vo2_max":                  self.vo2_max,
            "acwr":                     self.acwr,
            "hrv_7d_slope":             self.hrv_7d_slope,
            "sleep_efficiency_delta":   self.sleep_efficiency_delta,
            "rhr_7d_slope":             self.rhr_7d_slope,
        }
