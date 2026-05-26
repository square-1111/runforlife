"""
Ingestion pipeline: raw Garmin data → DailyDocument → SQLite.

Flow per date:
  1. collector.collect_day() → raw dicts from Garmin
  2. _build_document() → DailyDocument (raw fields only)
  3. _enrich_features() → compute ACWR, HRV slope, sleep delta
     (reads prior rows from metrics_store — works correctly during
      backfill because earlier dates are stored first)
  4. metrics_store.upsert_day() → stored
"""

from runforlife.rag.daily_document import DailyDocument
from runforlife.rag.features import compute_sleep_efficiency_delta, linear_slope
from runforlife.storage.metrics_store import get_window, upsert_day
from runforlife.sync.collector import collect_day


def _parse_pace_to_seconds(pace_str: str | None) -> float | None:
    """Convert '4:35/km' → 275.0 seconds/km."""
    if not pace_str:
        return None
    try:
        pace_str = pace_str.replace("/km", "").strip()
        parts = pace_str.split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except Exception:
        return None


def _build_document(user: str, date: str, raw: dict) -> DailyDocument:
    """Map raw collector output to a DailyDocument (no feature computation)."""
    doc = DailyDocument(user=user, date=date)

    # Sleep
    sleep = raw.get("sleep")
    if sleep:
        durations = sleep.get("sleep_duration", {})
        total_str = durations.get("total", "")
        if total_str and ":" in total_str:
            h, m = total_str.split(":")
            doc.sleep_duration_min = int(h) * 60 + int(m)
        score_data = sleep.get("sleep_score", {})
        if isinstance(score_data, dict):
            doc.sleep_score = score_data.get("value")

    # HRV
    hrv = raw.get("hrv")
    if hrv:
        hrv_data = hrv.get("hrv_data") or {}
        doc.hrv_last_night = hrv_data.get("last_night_average")

    # Heart rate
    hr = raw.get("heart_rate")
    if hr:
        doc.resting_hr = hr.get("resting_hr")

    # Training status (has ACWR via load_ratio)
    ts = raw.get("training_status")
    if ts:
        load_ratio = ts.get("load_ratio")
        if load_ratio is not None:
            doc.acwr = float(load_ratio)

    # Training readiness
    tr = raw.get("training_readiness")
    if tr:
        doc.readiness_score = tr.get("readiness_score") or tr.get("score")

    # Body battery
    bb = raw.get("body_battery")
    if bb:
        readings = bb.get("readings") or []
        if readings:
            doc.body_battery_end = readings[-1].get("charged") or readings[-1].get("value")

    # Activities (running)
    activities = raw.get("activities")
    if activities:
        runs = [a for a in (activities.get("activities") or []) if "running" in a.get("type", "")]
        if runs:
            doc.ran_today = True
            doc.run_distance_km = sum(r.get("distance_km", 0) for r in runs)
            main_run = max(runs, key=lambda r: r.get("distance_km", 0))
            doc.run_avg_pace_sec_per_km = _parse_pace_to_seconds(main_run.get("avg_pace"))
            doc.run_avg_hr = main_run.get("avg_hr")
            doc.training_effect_aerobic = main_run.get("training_effect_aerobic")

    return doc


def _enrich_features(doc: DailyDocument) -> None:
    """
    Compute window-based features from already-stored history.

    Reads prior rows from SQLite rather than Garmin — cheaper, and works
    correctly during backfill since earlier dates are ingested first.
    """
    user = doc.user

    # HRV and RHR 7-day slopes
    rows_7 = get_window(user, doc.date, 7)
    hrv_window = [r.get("hrv_last_night") for r in rows_7]
    doc.hrv_7d_slope = linear_slope(hrv_window)

    rhr_window = [r.get("resting_hr") for r in rows_7]
    doc.rhr_7d_slope = linear_slope(rhr_window)

    # Sleep efficiency delta vs 28-day baseline
    rows_28 = get_window(user, doc.date, 28)
    score_window = [r.get("sleep_score") for r in rows_28]
    doc.sleep_efficiency_delta = compute_sleep_efficiency_delta(doc.sleep_score, score_window)


def ingest_day(user: str, date: str, delay_seconds: float = 1.0) -> DailyDocument | None:
    """
    Full pipeline for a single date: collect → build → enrich → store.

    Returns the ingested DailyDocument, or None if no data was available.
    """
    raw = collect_day(user, date, delay_seconds=delay_seconds)

    if not any(v is not None for v in raw.values()):
        return None

    doc = _build_document(user, date, raw)
    _enrich_features(doc)
    upsert_day(user, doc)

    return doc
