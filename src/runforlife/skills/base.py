"""
SKILL BASE CLASS
=================
Every skill inherits from this. It enforces the contract:
  - Every skill must have a NAME, DESCRIPTION, and INPUT_SCHEMA
  - Every skill must implement execute()
  - The base class handles converting the skill to Anthropic's tool format

WHY A BASE CLASS?
  Without it, each skill would define its own dict format for the tool
  definition. One might use "parameters", another "input_schema", another
  might forget the description. The base class prevents that drift.

  This is the thinnest useful abstraction — just enough structure to
  prevent mistakes, not so much that it obscures what's happening.
"""

from abc import ABC, abstractmethod
from typing import Any


class Skill(ABC):
    """Base class for all agent skills (tools)."""

    # Subclasses MUST set these
    name: str = ""
    description: str = ""
    input_schema: dict = {}

    @abstractmethod
    def execute(self, **kwargs: Any) -> dict:
        """Run the skill. Returns a dict the LLM can read."""
        ...

    def to_tool_definition(self) -> dict:
        """
        Convert to Anthropic's tool format.

        This is what gets sent to Claude in the `tools` parameter.
        Claude reads this to decide when/how to call the skill.

        Anthropic's format:
        {
            "name": "skill_name",
            "description": "what it does and when to use it",
            "input_schema": { JSON Schema for parameters }
        }
        """
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }
