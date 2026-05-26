"""
Rolling aggregation helpers for the ingestion pipeline.

These functions pull numeric metadata windows from Chroma so that
features.py can compute slopes and ratios without a separate timeseries DB.
"""

from datetime import date, timedelta


def date_range(end_date: str, days: int) -> list[str]:
    """Return list of ISO dates from (end_date - days) to end_date inclusive."""
    end = date.fromisoformat(end_date)
    return [(end - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]


def extract_field_window(docs_metadata: list[dict], field: str) -> list[float | None]:
    """
    Extract a numeric field from a list of ordered metadata dicts.

    Missing days or missing field values become None, preserving positional
    alignment needed for slope computation.
    """
    return [m.get(field) for m in docs_metadata]
