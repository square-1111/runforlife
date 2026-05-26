from typing import Any

from runforlife.skills.base import Skill
from runforlife.storage.memory_store import delete_memory, list_memories


class RecallMemory(Skill):
    name = "recall_memory"

    description = (
        "List all stored memories for a user, including expired ones. "
        "Use when the user asks 'what do you know about me?' or wants to review/delete stored facts. "
        "Note: active memories are already injected into the system prompt automatically — "
        "you only need this skill for explicit management or to find a memory_id to delete."
    )

    input_schema = {
        "type": "object",
        "properties": {
            "user": {
                "type": "string",
                "enum": ["tezuesh", "kakul"],
                "description": "Which athlete's memories to list",
            },
            "delete_id": {
                "type": "integer",
                "description": "Optional memory ID to delete. If provided, the memory is removed.",
            },
        },
        "required": ["user"],
    }

    def execute(self, **kwargs: Any) -> dict:
        user: str = kwargs["user"]
        delete_id: int | None = kwargs.get("delete_id")

        if delete_id is not None:
            deleted = delete_memory(user, delete_id)
            return {
                "success": True,
                "user": user,
                "action": "deleted",
                "memory_id": delete_id,
                "found": deleted,
            }

        memories = list_memories(user)
        return {
            "success": True,
            "user": user,
            "count": len(memories),
            "memories": memories,
        }
