"""
Ingestion pipeline: raw Garmin data → DailyDocument → SQLite.

Flow per date:
  1. collector.collect_day()  → raw dicts from Garmin
  2. _build_document()        → DailyDocument (raw fields only)
  3. _enrich_features()       → compute ACWR, HRV slope, sleep delta, RHR slope
     (reads prior rows from metrics_store — works correctly during
      backfill because earlier dates are stored first)
  4. metrics_store.upsert_day() → stored
"""

from runforlife.rag.daily_document import DailyDocument
from runforlife.rag.features import (
    compute_sleep_efficiency_delta,
    efficiency_factor,
    linear_slope,
)
from runforlife.storage.metrics_store import (
    get_window,
    upsert_activity_session,
    upsert_day,
)
from runforlife.sync.collector import SOURCE_KEYS, collect_day


def _pace_to_seconds(pace_str: str | None) -> float | None:
    """Convert '4:35/km' → 275.0 seconds/km."""
    if not pace_str:
        return None
    try:
        clean = pace_str.replace("/km", "").strip()
        parts = clean.split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except Exception:
        return None


def _time_from_local_ts(ts) -> str | None:
    """
    Extract HH:MM from a local timestamp.
    Accepts ISO string '2026-05-25T03:55:42.0' or millisecond epoch integer.
    """
    if ts is None:
        return None
    try:
        if isinstance(ts, (int, float)):
            # milliseconds since epoch → UTC datetime → format
            # Garmin local timestamps are labeled 'local' but stored as epoch ms
            from datetime import datetime, timezone
            dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
            return dt.strftime("%H:%M")
        # String: "2026-05-25T03:55:42.0"
        return str(ts)[11:16]
    except Exception:
        return None


def _run_temp_c(activity: dict) -> float | None:
    """Ambient temperature (°C) for a run, averaged from Garmin min/max if present.

    Garmin reports minTemperature/maxTemperature on outdoor activities (and the
    indoor room temp on treadmill runs). Returns the midpoint, or whichever bound
    is available, or None when the device logged no temperature.
    """
    lo = activity.get("minTemperature")
    hi = activity.get("maxTemperature")
    vals = [v for v in (lo, hi) if isinstance(v, (int, float))]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 1)


def _is_running(activity: dict) -> bool:
    """Whether a Garmin activity counts as a run (same test the run agg uses)."""
    type_key = (activity.get("activityType", {}) or {}).get("typeKey", "")
    return "running" in type_key.lower()


def _persist_activity_sessions(user: str, date: str, activities: list) -> None:
    """Persist every NON-running activity to the activity_sessions table.

    Strength / SkiErg / sled / HIIT / cycling are dropped by the run-centric
    daily_metrics aggregation. Capture them here without touching run_* fields.
    Running activities are deliberately skipped — they live in daily_metrics.
    """
    for a in activities:
        if not isinstance(a, dict) or _is_running(a):
            continue
        type_key = (a.get("activityType", {}) or {}).get("typeKey")
        if not type_key:
            continue  # can't key a session without a type

        dur_sec = a.get("duration")
        duration_min = round(dur_sec / 60, 1) if dur_sec else None
        avg_hr = a.get("averageHR")
        max_hr = a.get("maxHR")
        dist_m = a.get("distance")
        upsert_activity_session(
            user,
            date=date,
            activity_type=type_key,
            start=a.get("startTimeLocal") or "",
            duration_min=duration_min,
            avg_hr=round(avg_hr) if avg_hr else None,
            max_hr=round(max_hr) if max_hr else None,
            training_load=a.get("activityTrainingLoad"),
            distance_km=round(dist_m / 1000, 2) if dist_m else None,
        )


def _build_document(user: str, date: str, raw: dict) -> DailyDocument:
    """Map raw collector output to a DailyDocument (no feature computation)."""
    doc = DailyDocument(user=user, date=date)

    # ── Sleep ────────────────────────────────────────────────────────────────
    sleep_raw = raw.get("sleep")
    if isinstance(sleep_raw, dict):
        dto = sleep_raw.get("dailySleepDTO", {}) or {}

        # Duration: sleepTimeSeconds (already verified accurate for backfill)
        secs = dto.get("sleepTimeSeconds")
        if secs:
            doc.sleep_duration_min = round(secs / 60, 1)

        # Score
        scores = dto.get("sleepScores", {}) or {}
        overall = scores.get("overall", {}) or {}
        doc.sleep_score = overall.get("value")

        # Stages (convert seconds → whole minutes)
        deep = dto.get("deepSleepSeconds")
        rem  = dto.get("remSleepSeconds")
        light = dto.get("lightSleepSeconds")
        doc.deep_sleep_min  = round(deep / 60)  if deep  else None
        doc.rem_sleep_min   = round(rem / 60)   if rem   else None
        doc.light_sleep_min = round(light / 60) if light else None

        # Bedtime (local timestamp → "HH:MM")
        doc.sleep_start_local = _time_from_local_ts(
            dto.get("sleepStartTimestampLocal")
        )

        # Sleep HR and respiration
        avg_hr = dto.get("avgHeartRate")
        doc.sleep_hr_avg = round(avg_hr) if avg_hr else None
        doc.respiration_avg = dto.get("averageRespirationValue")

    # ── HRV ──────────────────────────────────────────────────────────────────
    hrv_raw = raw.get("hrv")
    if isinstance(hrv_raw, dict):
        summary = hrv_raw.get("hrvSummary", {}) or {}
        doc.hrv_last_night = summary.get("lastNightAvg")
        doc.hrv_weekly_avg = summary.get("weeklyAvg")
        doc.hrv_5min_high  = summary.get("lastNight5MinHigh")
        doc.hrv_garmin_status = summary.get("status")  # "BALANCED" | "UNBALANCED" | "LOW"

        baseline = summary.get("baseline", {}) or {}
        doc.hrv_baseline_low  = baseline.get("balancedLow")
        doc.hrv_baseline_high = baseline.get("balancedUpper")

    # ── User Summary (RHR, stress, body battery, steps) ──────────────────────
    summ = raw.get("summary")
    if isinstance(summ, dict):
        doc.resting_hr        = summ.get("restingHeartRate")
        doc.stress_avg        = summ.get("averageStressLevel")
        doc.stress_max        = summ.get("maxStressLevel")
        doc.stress_qualifier  = summ.get("stressQualifier")  # "CALM" | "BALANCED" | ...
        doc.body_battery_morning = summ.get("bodyBatteryAtWakeTime")
        doc.body_battery_peak    = summ.get("bodyBatteryHighestValue")
        doc.body_battery_end     = summ.get("bodyBatteryMostRecentValue")
        doc.steps            = summ.get("totalSteps")
        doc.active_calories  = summ.get("activeKilocalories")
        if doc.active_calories is not None:
            doc.active_calories = round(doc.active_calories)

    # ── Activities (all types from get_activities_by_date) ───────────────────
    activities = raw.get("activities")
    if isinstance(activities, list):
        runs = [
            a for a in activities
            if isinstance(a, dict)
            and "running" in (a.get("activityType", {}) or {}).get("typeKey", "").lower()
        ]
        if runs:
            doc.ran_today = True
            doc.run_distance_km = round(
                sum((a.get("distance") or 0) / 1000 for a in runs), 2
            )
            main_run = max(runs, key=lambda a: a.get("distance") or 0)

            # Pace: averageSpeed in m/s → sec/km
            speed = main_run.get("averageSpeed")
            if speed and speed > 0:
                doc.run_avg_pace_sec_per_km = round(1000 / speed)

            avg_hr = main_run.get("averageHR")
            doc.run_avg_hr = round(avg_hr) if avg_hr else None
            doc.training_effect_aerobic = main_run.get("aerobicTrainingEffect")

            # Environment: treadmill/indoor vs outdoor, and ambient temperature.
            # Both unconfound pace/EF trends (treadmill pace ≠ outdoor; heat tax).
            type_key = (main_run.get("activityType", {}) or {}).get("typeKey", "").lower()
            doc.run_is_indoor = ("treadmill" in type_key) or ("indoor" in type_key)
            doc.run_temp_c = _run_temp_c(main_run)

            # Efficiency Factor (speed/HR) — aerobic-progress signal that raw pace hides.
            doc.run_efficiency_factor = efficiency_factor(
                doc.run_avg_pace_sec_per_km, doc.run_avg_hr
            )

        # Capture non-running activities (strength, Hyrox stations, cycling…)
        # into the sibling activity_sessions table. This is separate from the
        # run aggregation above and leaves run_* / daily_metrics untouched.
        _persist_activity_sessions(user, date, activities)

    # ── VO2max ───────────────────────────────────────────────────────────────
    vo2_raw = raw.get("vo2max")
    if isinstance(vo2_raw, list) and vo2_raw:
        generic = vo2_raw[0].get("generic", {}) or {}
        doc.vo2_max = generic.get("vo2MaxPreciseValue")

    return doc


def _enrich_features(doc: DailyDocument) -> None:
    """
    Compute window-based features from already-stored history.

    Reads prior rows from SQLite rather than Garmin — cheaper, and works
    correctly during backfill since earlier dates are ingested first.
    """
    user = doc.user

    # 7-day slopes for HRV and RHR
    rows_7 = get_window(user, doc.date, 7)
    doc.hrv_7d_slope = linear_slope([r.get("hrv_last_night") for r in rows_7])
    doc.rhr_7d_slope = linear_slope([r.get("resting_hr") for r in rows_7])

    # Sleep efficiency delta vs 28-day baseline
    rows_28 = get_window(user, doc.date, 28)
    doc.sleep_efficiency_delta = compute_sleep_efficiency_delta(
        doc.sleep_score, [r.get("sleep_score") for r in rows_28]
    )

    # ACWR: 7-day avg load / 28-day avg load.
    #
    # Load proxy = run_distance_km (0 on rest days) — the *distance-only* basis.
    # This is deliberately NOT the pace-weighted features.daily_load() used by
    # the Banister model: ACWR is a ratio of rolling averages, so pace-weighting
    # every day would change every stored acwr value. Per the conservative
    # single-source rule we keep the distance basis here and let banister own the
    # pace-weighted definition. If ACWR ever moves to pace-weighted load, swap
    # this line for features.daily_load(dist, pace).value and re-baseline.
    loads_28 = [r.get("run_distance_km") or 0.0 for r in rows_28]
    loads_7  = loads_28[-7:] if len(loads_28) >= 7 else loads_28
    avg_7  = sum(loads_7)  / len(loads_7)  if loads_7  else 0.0
    avg_28 = sum(loads_28) / len(loads_28) if loads_28 else 0.0
    if avg_28 > 0:
        doc.acwr = round(avg_7 / avg_28, 3)


def ingest_day(user: str, date: str, delay_seconds: float = 0.3) -> DailyDocument | None:
    """
    Full pipeline for a single date: collect → build → enrich → store.

    Returns the ingested DailyDocument, or None if no data was available.
    """
    raw = collect_day(user, date, delay_seconds=delay_seconds)

    # Only the real data sources count toward "is there anything here" — ignore
    # the _provenance map collect_day attaches. A day where every source errored
    # or is empty produces no row (rather than a skeleton).
    if not any(raw.get(k) is not None for k in SOURCE_KEYS):
        return None

    doc = _build_document(user, date, raw)
    _enrich_features(doc)
    upsert_day(user, doc)

    return doc
