"""
RunForLife FastAPI server.

Serves both athletes from any device via HTTP.

Endpoints:
  POST /chat          — Send a message, get a coaching response
  GET  /health        — Health check + doc count per user
  GET  /memories/{user}  — List stored memories for a user

Run locally:
  uv run uvicorn runforlife.server:app --host 0.0.0.0 --port 8000

Run on VPS (systemd service manages this):
  uvicorn runforlife.server:app --host 0.0.0.0 --port 8000 --workers 1

Security note:
  For 2-user private deployment, bind to localhost and use an nginx
  reverse proxy with basic auth, or add the API_KEY check below.
  DO NOT expose port 8000 directly to the internet without auth.
"""

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from runforlife.agent.core import Agent
from runforlife.config import CONVERSATION_WINDOW
from runforlife.storage.paths import is_valid_athlete, list_athletes
from runforlife.skills.registry import create_default_registry
from runforlife.storage.conversation_db import load_recent, save_message
from runforlife.storage.profile_store import build_system_prompt

load_dotenv()

# ── Per-user agent instances (one per user, reused across requests) ────────
_agents: dict[str, Agent] = {}
_registry = None


def _get_or_create_agent(user: str) -> Agent:
    if user not in _agents:
        global _registry
        if _registry is None:
            _registry = create_default_registry()

        history = load_recent(user, n=CONVERSATION_WINDOW)
        system_prompt = build_system_prompt(user)
        _agents[user] = Agent(_registry, system_prompt=system_prompt, initial_conversation=history)
    return _agents[user]


# ── Optional API key auth ──────────────────────────────────────────────────
_API_KEY = os.environ.get("RUNFORLIFE_API_KEY")


def _check_api_key(request: Request) -> None:
    if not _API_KEY:
        return  # No key configured — open access (use firewall on VPS)
    key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
    if key != _API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ── App ────────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Pre-warm agents for every configured athlete on startup
    for user in list_athletes():
        _get_or_create_agent(user)
    yield


app = FastAPI(
    title="RunForLife Coach",
    description="AI running coach for Tezuesh & Kakul",
    version="0.1.0",
    lifespan=lifespan,
)


# ── Request / Response models ──────────────────────────────────────────────
class ChatRequest(BaseModel):
    user: str
    message: str


class ChatResponse(BaseModel):
    user: str
    message: str
    response: str


class HealthResponse(BaseModel):
    status: str
    users: dict


# ── Endpoints ──────────────────────────────────────────────────────────────
@app.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    _: None = Depends(_check_api_key),
) -> ChatResponse:
    if not is_valid_athlete(body.user):
        raise HTTPException(status_code=400, detail=f"Unknown user: {body.user}. Must be one of {list_athletes()}")

    if not body.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    agent = _get_or_create_agent(body.user)

    try:
        response = agent.chat(body.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {e}") from e

    save_message(body.user, "user", body.message)
    save_message(body.user, "assistant", response)

    return ChatResponse(user=body.user, message=body.message, response=response)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    from runforlife.storage.metrics_store import count_days

    user_info = {}
    for user in list_athletes():
        history = load_recent(user, n=2)
        user_info[user] = {
            "agent_loaded": user in _agents,
            "history_messages": len(history),
            "synced_days": count_days(user),
        }

    return HealthResponse(status="ok", users=user_info)


@app.get("/memories/{user}")
async def get_memories(
    user: str,
    _: None = Depends(_check_api_key),
) -> JSONResponse:
    if not is_valid_athlete(user):
        raise HTTPException(status_code=404, detail=f"Unknown user: {user}")

    from runforlife.storage.memory_store import list_memories
    memories = list_memories(user)
    return JSONResponse({"user": user, "count": len(memories), "memories": memories})
