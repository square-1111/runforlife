"""
Post-session signal extraction for the personality model.

After every coordinator.chat() call, a cheap Haiku call extracts
behavioral signals that feed the personality model update loop.
"""

import json
from dataclasses import dataclass

import anthropic


@dataclass
class SessionSignals:
    user_engaged: bool
    pushed_back: bool
    asked_followup: bool
    preferred_detail: str       # "low" | "medium" | "high"
    responded_to_narrative: bool
    life_context_mentioned: str # non-empty text if user shared personal context
    ignored_recommendation: bool


_REFLECTION_SYSTEM = """\
You extract behavioral signals from one coaching conversation turn.
Return ONLY valid JSON with exactly these fields (no markdown, no prose):
{
  "user_engaged": bool,
  "pushed_back": bool,
  "asked_followup": bool,
  "preferred_detail": "low" | "medium" | "high",
  "responded_to_narrative": bool,
  "life_context_mentioned": "<text or empty string>",
  "ignored_recommendation": bool
}

Definitions:
- user_engaged: user gave substantive reply, showed interest, or asked something meaningful
- pushed_back: user disagreed, corrected the coach, or said something was wrong/unwanted
- asked_followup: user asked a follow-up question or probed deeper
- preferred_detail: low=user wants brief summary, high=user wants deep data/numbers, medium=neither clear
- responded_to_narrative: user engaged positively with motivational framing or storytelling
- life_context_mentioned: any personal context mentioned (stress, travel, illness, work) — empty string if none
- ignored_recommendation: user explicitly dismissed or rejected a coaching recommendation"""


def extract_session_signals(user_message: str, assistant_response: str) -> SessionSignals:
    """Extract behavioral signals from one conversation turn. ~200 tokens via Haiku."""
    client = anthropic.Anthropic()
    prompt = f"USER: {user_message}\n\nASSISTANT: {assistant_response}"

    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        system=_REFLECTION_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    try:
        data = json.loads(resp.content[0].text.strip())
    except (json.JSONDecodeError, IndexError, AttributeError):
        return _default_signals()

    return SessionSignals(
        user_engaged=bool(data.get("user_engaged", True)),
        pushed_back=bool(data.get("pushed_back", False)),
        asked_followup=bool(data.get("asked_followup", False)),
        preferred_detail=data.get("preferred_detail", "medium"),
        responded_to_narrative=bool(data.get("responded_to_narrative", False)),
        life_context_mentioned=str(data.get("life_context_mentioned", "")),
        ignored_recommendation=bool(data.get("ignored_recommendation", False)),
    )


def _default_signals() -> SessionSignals:
    return SessionSignals(
        user_engaged=True, pushed_back=False, asked_followup=False,
        preferred_detail="medium", responded_to_narrative=False,
        life_context_mentioned="", ignored_recommendation=False,
    )
