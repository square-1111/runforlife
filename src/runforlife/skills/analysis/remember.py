from typing import Any

from runforlife.skills.base import Skill
from runforlife.storage.memory_store import save_memory


class Remember(Skill):
    name = "remember"

    description = (
        "Store a durable fact or context about the user that should persist across sessions. "
        "Use this when the user mentions something important: travel plans, injuries, race goals, "
        "how they felt during a session, decisions about training approach, etc. "
        "These memories are automatically injected into future sessions — the user won't need to repeat themselves. "
        "Examples: 'travelling to Singapore May 28-June 3', 'left knee tight this week', "
        "'targeting 4:05/km pace for Sunday long run'."
    )

    input_schema = {
        "type": "object",
        "properties": {
            "user": {
                "type": "string",
                "enum": ["tezuesh", "kakul"],
                "description": "Which athlete this memory belongs to",
            },
            "content": {
                "type": "string",
                "description": "The fact to remember. Be specific and concise (1-2 sentences).",
            },
            "expires_on": {
                "type": "string",
                "description": "Optional ISO date (YYYY-MM-DD) when this memory becomes stale. "
                               "Set for time-bounded facts like travel or temporary injuries.",
            },
        },
        "required": ["user", "content"],
    }

    def execute(self, **kwargs: Any) -> dict:
        user: str = kwargs["user"]
        content: str = kwargs["content"]
        expires_on: str | None = kwargs.get("expires_on")

        memory_id = save_memory(user, content, expires_on)

        return {
            "success": True,
            "user": user,
            "memory_id": memory_id,
            "content": content,
            "expires_on": expires_on,
            "message": f"Remembered: {content}",
        }
