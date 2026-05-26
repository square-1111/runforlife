"""
SKILL: garmin_auth
==================
YOUR FIRST SKILL — read the comments carefully.

A skill has TWO audiences:
  1. The LLM (reads name + description + input_schema to decide when/how to call it)
  2. Python runtime (executes the actual code)

The LLM NEVER sees the code inside execute(). It only sees:
  - The name and description (from to_tool_definition)
  - The return value (after execution)

Think of it like ordering at a restaurant:
  - Menu (to_tool_definition) → customer reads this to decide what to order
  - Kitchen (execute) → customer never sees this
  - Plate (return value) → customer only sees the result
"""

import os
from pathlib import Path
from typing import Any

from garminconnect import Garmin

from runforlife.skills.base import Skill

# Where we store auth tokens so we don't re-login every time
TOKENS_DIR = Path(__file__).parent.parent.parent.parent.parent / "tokens"

# In-memory session cache so other skills can reuse authenticated sessions
_sessions: dict[str, Garmin] = {}


def get_session(user: str) -> Garmin:
    """Get an authenticated Garmin session. Used by other skills internally."""
    if user in _sessions:
        return _sessions[user]
    raise ValueError(f"No session for '{user}'. Call garmin_auth first.")


class GarminAuth(Skill):
    """Authenticate with Garmin Connect."""

    name = "garmin_auth"

    description = (
        "Authenticate with Garmin Connect for a specific user. "
        "Call this BEFORE any other Garmin data skill. "
        "Returns whether authentication was successful. "
        "Tokens are cached — subsequent calls are fast."
    )

    input_schema = {
        "type": "object",
        "properties": {
            "user": {
                "type": "string",
                "enum": ["tezuesh", "kakul"],
                "description": "Which athlete to authenticate",
            }
        },
        "required": ["user"],
    }

    def _get_credentials(self, user: str) -> tuple[str, str]:
        key = user.upper()
        email = os.environ.get(f"GARMIN_EMAIL_{key}")
        password = os.environ.get(f"GARMIN_PASSWORD_{key}")
        if not email or not password:
            raise ValueError(
                f"Set GARMIN_EMAIL_{key} and GARMIN_PASSWORD_{key} in .env"
            )
        return email, password

    def execute(self, **kwargs: Any) -> dict:
        user: str = kwargs["user"]

        # Fast path: reuse in-memory session
        if user in _sessions:
            return {
                "success": True,
                "user": user,
                "method": "in_memory",
                "display_name": _sessions[user].display_name,
            }

        token_path = TOKENS_DIR / user
        token_file = token_path / "garmin_tokens.json"
        email, password = self._get_credentials(user)
        garmin = Garmin(email, password)

        # Attempt 1: Load cached tokens (fast, no full re-login)
        if token_file.exists():
            try:
                garmin.login(tokenstore=str(token_path))
                garmin.client.dump(str(token_path))  # refresh token on disk
                _sessions[user] = garmin
                return {
                    "success": True,
                    "user": user,
                    "method": "cached_tokens",
                    "display_name": garmin.display_name,
                }
            except Exception:
                pass  # Tokens expired — fall through to fresh login

        # Attempt 2: Fresh login with credentials
        try:
            mfa_status, _ = garmin.login()
            if mfa_status == "needs_mfa":
                return {
                    "success": False,
                    "user": user,
                    "error": (
                        "MFA required. Authenticate interactively first: "
                        f"uv run python -m runforlife.auth {user}"
                    ),
                }
            token_path.mkdir(parents=True, exist_ok=True)
            garmin.client.dump(str(token_path))
            _sessions[user] = garmin
            return {
                "success": True,
                "user": user,
                "method": "fresh_login",
                "display_name": garmin.display_name,
            }
        except Exception as e:
            return {"success": False, "user": user, "error": str(e)}
