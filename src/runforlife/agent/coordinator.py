"""
Coordinator — routes each user message to the right specialist agent.

Flow per message:
  1. Classify the message with a fast Haiku call (no tools, ~50 tokens)
  2. Build the specialist agent (correct persona + tool subset)
  3. Load fresh conversation history so every specialist has full context
  4. Run the specialist's tool loop
  5. Persist the exchange to conversation history

Using Haiku for classification keeps latency and cost minimal.
The specialist itself uses Sonnet (or whatever MODEL is configured).
"""

import os

import anthropic

from runforlife.agent.core import Agent
from runforlife.agent.specialists import (
    ALL_DOMAINS,
    ANALYTICS,
    PROMPT_BUILDERS,
    RECOVERY,
    REGISTRY_FACTORIES,
    TRAINING,
)
from runforlife.config import CONVERSATION_WINDOW, MODEL
from runforlife.storage.conversation_db import load_recent, save_message

_CLASSIFY_SYSTEM = """\
You are a routing agent. Classify the athlete's message into exactly one category.

Categories:
- recovery   : sleep, HRV, body battery, stress, injury risk, readiness, rest days
- training   : mileage, runs, workouts, training load, ACWR, gear, streaks, consistency
- race       : VO2max, race predictions, goal time, fitness level, race strategy, pace targets
- analytics  : correlations, patterns, statistics, SQL queries, data exploration, custom questions

Reply with a single word: recovery, training, race, or analytics."""

_DOMAIN_LABELS = {
    "recovery": "Recovery Specialist",
    "training": "Training Planner",
    "race": "Race Strategist",
    "analytics": "Data Analyst",
}


def _classify(message: str) -> str:
    """Fast intent classification using Haiku."""
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=10,
        system=_CLASSIFY_SYSTEM,
        messages=[{"role": "user", "content": message}],
    )
    domain = response.content[0].text.strip().lower()
    return domain if domain in ALL_DOMAINS else TRAINING  # safe default


class Coordinator:
    """
    Routes messages to specialist agents.

    Each message gets a fresh specialist with current conversation history —
    this ensures all specialists always have full context regardless of which
    domain handled the previous turn.
    """

    def __init__(self, user: str, model: str = MODEL) -> None:
        self.user = user
        self.model = model

    def chat(self, message: str) -> tuple[str, str]:
        """
        Process a message. Returns (domain_label, response_text).

        The domain_label is shown in the CLI so the user knows which
        specialist answered (e.g. '[Recovery Specialist]').
        """
        domain = _classify(message)

        history = load_recent(self.user, n=CONVERSATION_WINDOW)
        registry = REGISTRY_FACTORIES[domain]()
        system_prompt = PROMPT_BUILDERS[domain](self.user)

        agent = Agent(
            registry,
            model=self.model,
            system_prompt=system_prompt,
            initial_conversation=history,
        )

        response = agent.chat(message)

        save_message(self.user, "user", message)
        save_message(self.user, "assistant", response)

        return _DOMAIN_LABELS[domain], response
