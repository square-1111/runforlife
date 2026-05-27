"""
Per-user personality model — persisted as JSON, updated after each session.

Dimensions tracked:
  communication    : "direct_blunt" | "balanced" | "supportive_narrative"
  data_depth       : "low" | "medium" | "high"
  pushback_tolerance: "low" | "medium" | "high"
  plan_style       : "structured" | "principles_adaptive"

Update rule (PAMU-lite):
  - Count signals per dimension value
  - Promote a value when it has ≥3 signals AND ≥60% of that dimension's total
  - Confidence = min(1.0, total_signals / 20)  — fully formed at 20 signals
  - Below 0.2 confidence → emit no coaching style block (neutral defaults)
"""

import json
from datetime import date
from typing import TYPE_CHECKING

from runforlife.storage.paths import personality_path

if TYPE_CHECKING:
    from runforlife.agent.reflection import SessionSignals


_DEFAULT: dict = {
    "archetype":           "unknown",
    "communication":       "balanced",
    "data_depth":          "medium",
    "pushback_tolerance":  "medium",
    "plan_style":          "structured",
    "motivation_driver":   "unknown",
    "confidence":          0.0,
    "signal_counts": {
        "communication":      {},
        "data_depth":         {},
        "pushback_tolerance": {},
        "plan_style":         {},
    },
    "last_updated": None,
}


def load_personality(user: str) -> dict:
    """Load model from disk. Returns defaults if no model exists yet."""
    path = personality_path(user)
    if path.exists():
        saved = json.loads(path.read_text())
        # Backfill missing keys from default (schema evolution)
        merged = dict(_DEFAULT)
        merged.update(saved)
        merged["signal_counts"] = {**_DEFAULT["signal_counts"], **saved.get("signal_counts", {})}
        return merged
    return {k: (list(v) if isinstance(v, list) else dict(v) if isinstance(v, dict) else v)
            for k, v in _DEFAULT.items()}


def save_personality(user: str, model: dict) -> None:
    model["last_updated"] = date.today().isoformat()
    personality_path(user).write_text(json.dumps(model, indent=2))


def update_personality(user: str, signals: "SessionSignals") -> None:
    """Update personality model from one session's signals. Saves to disk."""
    model = load_personality(user)
    counts = model["signal_counts"]

    # data_depth
    detail = signals.preferred_detail
    if detail in ("low", "medium", "high"):
        _record(counts, "data_depth", detail)
        _maybe_promote(model, "data_depth", counts["data_depth"])

    # communication
    if signals.pushed_back:
        _record(counts, "communication", "direct_blunt")
        _maybe_promote(model, "communication", counts["communication"])
    elif signals.responded_to_narrative:
        _record(counts, "communication", "supportive_narrative")
        _maybe_promote(model, "communication", counts["communication"])
    elif signals.user_engaged and not signals.pushed_back:
        _record(counts, "communication", "balanced")
        _maybe_promote(model, "communication", counts["communication"])

    # pushback_tolerance — high if user ignored recommendations
    if signals.ignored_recommendation:
        _record(counts, "pushback_tolerance", "high")
        _maybe_promote(model, "pushback_tolerance", counts["pushback_tolerance"])

    # plan_style — asked_followup suggests wanting deeper explanations
    if signals.asked_followup:
        _record(counts, "plan_style", "principles_adaptive")
        _maybe_promote(model, "plan_style", counts["plan_style"])

    # Confidence: grows as total signals accumulate
    total = sum(sum(d.values()) for d in counts.values() if isinstance(d, dict))
    model["confidence"] = round(min(1.0, total / 20.0), 3)

    # Auto-save life context to memory store
    if signals.life_context_mentioned:
        _save_life_context(user, signals.life_context_mentioned)

    save_personality(user, model)


def coaching_style_block(user: str) -> str:
    """
    Return coaching style instructions to append to specialist system prompts.
    Returns empty string until confidence ≥ 0.2 (at least ~4 accumulated signals).
    """
    model = load_personality(user)
    if model.get("confidence", 0.0) < 0.2:
        return ""

    communication = model.get("communication", "balanced")
    data_depth = model.get("data_depth", "medium")
    plan_style = model.get("plan_style", "structured")
    lines = ["\n## Coaching Style for This Athlete"]

    if communication == "direct_blunt":
        lines += [
            "- Lead with numbers. Skip narrative framing.",
            "- No motivational language. No rhetorical questions.",
            "- Format: Day / Workout / Pace / Distance. Nothing else.",
        ]
    elif communication == "supportive_narrative":
        lines += [
            "- Explain the why behind every recommendation.",
            "- Connect today's session to the bigger journey.",
            "- Use data to support the story, not as the lead.",
        ]
    else:
        lines.append("- Balance data with context. Keep explanations concise.")

    if data_depth == "high":
        lines.append("- Include raw numbers and full analysis. This athlete wants depth.")
    elif data_depth == "low":
        lines.append("- Keep it brief. Bottom line only — skip the analysis.")

    if plan_style == "principles_adaptive":
        lines.append("- Give principles and reasoning. This athlete designs their own sessions.")

    return "\n".join(lines)


def _record(counts: dict, dimension: str, value: str) -> None:
    dim = counts.setdefault(dimension, {})
    dim[value] = dim.get(value, 0) + 1


def _maybe_promote(model: dict, dimension: str, counts: dict) -> None:
    """Promote a dimension value when it dominates (≥3 signals, ≥60% share)."""
    if not counts:
        return
    top = max(counts, key=counts.__getitem__)
    top_count = counts[top]
    total = sum(counts.values())
    if top_count >= 3 and top_count >= total * 0.6:
        model[dimension] = top


def _save_life_context(user: str, context: str) -> None:
    try:
        from runforlife.storage.memory_store import save_memory
        save_memory(user, f"[life context] {context}")
    except Exception:
        pass
