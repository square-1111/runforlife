#!/usr/bin/env python3
"""
Stop hook for the RunForLife coach plugin (Phase 2) — the self-improvement write path.

When a coaching session ends, this hook closes the learning loop:

  1. Determine the active athlete (~/.runforlife/active_athlete). If none, exit 0.
  2. Best-effort parse the session transcript (JSONL at transcript_path) to recover
     the LAST real user message and the LAST assistant text reply.
  3. If both are found AND ANTHROPIC_API_KEY is available, run the cheap Haiku signal
     extractor (reflection.extract_session_signals) and feed the result into the
     atomic, flock-guarded personality update (personality_store.update_personality).
     Missing key / any failure here is swallowed silently — learning is optional.
  4. ALWAYS finish by pruning expired ephemeral context (athlete_memory.prune_ephemeral).

Every step is wrapped so the hook NEVER crashes the user's session. main() always
returns 0. A crashing Stop hook must never break Claude Code, so failures are
absorbed and (at most) reported as a short warning line.
"""

import json
import sys
from pathlib import Path

# hooks/ -> runforlife-coach/ -> repo root. The runforlife package lives in src/,
# and the repo's .env (with ANTHROPIC_API_KEY) sits at the repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC_DIR = _REPO_ROOT / "src"
_ENV_FILE = _REPO_ROOT / ".env"

# Roles that carry a turn's message payload in the transcript.
_USER_ROLE = "user"
_ASSISTANT_ROLE = "assistant"


def _ensure_src_on_path() -> None:
    """Make the runforlife package importable from the repo's src/ dir."""
    src = str(_SRC_DIR)
    if src not in sys.path:
        sys.path.insert(0, src)


def _read_stdin_json() -> dict:
    """Parse the hook's STDIN JSON payload. Returns {} on any problem."""
    try:
        raw = sys.stdin.read()
    except Exception:  # noqa: BLE001 - stdin may be closed/unavailable
        return {}
    if not raw or not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _read_active_athlete() -> str | None:
    """Return the active athlete name, or None if unset/empty/missing."""
    from runforlife.storage.paths import active_athlete_file

    path = active_athlete_file()
    if not path.exists():
        return None
    name = path.read_text(encoding="utf-8").strip()
    return name or None


def _extract_text(content: object) -> str:
    """Pull plain human/assistant text out of a transcript message's content.

    Content may be a bare string or a list of typed blocks (text / thinking /
    tool_use / tool_result). Only true text blocks contribute; tool_use,
    tool_result, and thinking blocks are ignored so we capture the actual
    conversational turn rather than tool plumbing. Returns "" if nothing usable.
    """
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "text":
                continue
            text = block.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
        return "\n".join(parts).strip()

    return ""


def _is_tool_result_only(content: object) -> bool:
    """True if a user turn is purely tool_result blocks (i.e. not a human prompt)."""
    if not isinstance(content, list):
        return False
    blocks = [b for b in content if isinstance(b, dict)]
    if not blocks:
        return False
    return all(b.get("type") == "tool_result" for b in blocks)


def _read_last_turns(transcript_path: str) -> tuple[str | None, str | None]:
    """Return (last_user_message, last_assistant_text) from the JSONL transcript.

    Best-effort and schema-defensive: each line is an independent JSON object and
    real conversation turns live under obj["message"] with a "role". Lines that
    fail to parse are skipped. Tool-result-only user turns are skipped so we keep
    a genuine human prompt. Either element may be None if not found.
    """
    if not transcript_path:
        return None, None

    path = Path(transcript_path)
    if not path.exists() or not path.is_file():
        return None, None

    last_user: str | None = None
    last_assistant: str | None = None

    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if not isinstance(obj, dict):
                    continue

                message = obj.get("message")
                if not isinstance(message, dict):
                    continue

                role = message.get("role")
                content = message.get("content")

                if role == _USER_ROLE:
                    if _is_tool_result_only(content):
                        continue
                    text = _extract_text(content)
                    if text:
                        last_user = text
                elif role == _ASSISTANT_ROLE:
                    text = _extract_text(content)
                    if text:
                        last_assistant = text
    except Exception:  # noqa: BLE001 - transcript read must never crash the hook
        return last_user, last_assistant

    return last_user, last_assistant


def _learn_from_session(athlete: str, user_msg: str, assistant_resp: str) -> None:
    """Extract behavioral signals and update the personality model.

    Requires ANTHROPIC_API_KEY (loaded from the repo .env). If the key is absent
    or the Haiku call fails for any reason, this is skipped silently — the
    personality update is a best-effort enrichment, never a hard requirement.
    """
    import os

    try:
        from dotenv import load_dotenv

        # Point dotenv at the repo .env explicitly: a Stop hook's cwd is not
        # guaranteed to be the repo root, so a bare load_dotenv() may miss it.
        if _ENV_FILE.exists():
            load_dotenv(dotenv_path=_ENV_FILE)
        else:
            load_dotenv()
    except Exception:  # noqa: BLE001 - dotenv is optional; env may already be set
        pass

    if not os.environ.get("ANTHROPIC_API_KEY"):
        return

    try:
        from runforlife.agent import reflection
        from runforlife.storage import personality_store

        signals = reflection.extract_session_signals(user_msg, assistant_resp)
        personality_store.update_personality(athlete, signals)
    except Exception:  # noqa: BLE001 - learning is optional; never crash on failure
        return


def main() -> int:
    """Run the hook. Always returns 0 so a failure never blocks the session."""
    try:
        _ensure_src_on_path()

        athlete = _read_active_athlete()
        if athlete is None:
            return 0

        payload = _read_stdin_json()
        transcript_path = payload.get("transcript_path")
        if not isinstance(transcript_path, str):
            transcript_path = ""

        # Step 2/3: learn from the session (best-effort).
        try:
            user_msg, assistant_resp = _read_last_turns(transcript_path)
            if user_msg and assistant_resp:
                _learn_from_session(athlete, user_msg, assistant_resp)
        except Exception as exc:  # noqa: BLE001 - never crash the session
            print(f"[RunForLife] (warning: session reflection skipped: {exc})")

        # Step 4: always prune expired ephemeral context.
        try:
            from runforlife.storage import athlete_memory

            athlete_memory.prune_ephemeral(athlete)
        except Exception as exc:  # noqa: BLE001 - never crash the session
            print(f"[RunForLife] (warning: ephemeral prune skipped: {exc})")

        return 0
    except Exception as exc:  # noqa: BLE001 - last-resort guard, never crash
        print(f"[RunForLife] Stop hook warning: {exc}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
