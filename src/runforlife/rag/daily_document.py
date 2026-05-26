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
    sleep_efficiency: float | None = None  # 0-100 %

    # --- HRV & Heart Rate ---
    hrv_last_night: float | None = None  # ms
    resting_hr: int | None = None  # bpm

    # --- Recovery & Readiness ---
    readiness_score: int | None = None  # 0-100
    body_battery_end: int | None = None  # 0-100
    stress_avg: int | None = None  # 0-100

    # --- Training ---
    ran_today: bool = False
    run_distance_km: float | None = None
    run_avg_pace_sec_per_km: float | None = None
    run_avg_hr: int | None = None
    training_effect_aerobic: float | None = None

    # --- Computed features (populated by features.py during ingestion) ---
    acwr: float | None = None                    # Acute:Chronic Workload Ratio
    hrv_7d_slope: float | None = None            # ms/day (negative = declining)
    sleep_efficiency_delta: float | None = None  # vs 28d baseline (pp)
    rhr_7d_slope: float | None = None            # bpm/day over 7d

    def to_row(self) -> dict:
        """Flat dict for SQLite INSERT OR REPLACE."""
        return {
            "user_id": self.user,
            "date": self.date,
            "sleep_duration_min": self.sleep_duration_min,
            "sleep_score": self.sleep_score,
            "sleep_efficiency": self.sleep_efficiency,
            "hrv_last_night": self.hrv_last_night,
            "resting_hr": self.resting_hr,
            "readiness_score": self.readiness_score,
            "body_battery_end": self.body_battery_end,
            "stress_avg": self.stress_avg,
            "ran_today": int(self.ran_today),
            "run_distance_km": self.run_distance_km,
            "run_avg_pace_sec_per_km": self.run_avg_pace_sec_per_km,
            "run_avg_hr": self.run_avg_hr,
            "training_effect_aerobic": self.training_effect_aerobic,
            "acwr": self.acwr,
            "hrv_7d_slope": self.hrv_7d_slope,
            "sleep_efficiency_delta": self.sleep_efficiency_delta,
            "rhr_7d_slope": self.rhr_7d_slope,
        }
