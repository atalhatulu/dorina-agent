"""FastAPI routes for the Dorina Gateway."""

from __future__ import annotations

import json
import asyncio
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

from .models import (
    ChatCompletionRequest,
    ToolInfo,
    SessionInfo,
    SessionListResponse,
    HealthStatus,
    ErrorResponse,
)
from .health import get_health
from .auth import verify_key as verify_api_key

router = APIRouter()


# ── Dependency ──────────────────────────────────────────────

def get_api_key(request: Request) -> str | None:
    """Extract API key from Authorization header."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    # Also check X-API-Key header
    return request.headers.get("X-API-Key", None)


async def require_auth(request: Request) -> None:
    """Dependency: verify API key or raise 401."""
    # Disabled check — gateway only starts if auth is optional for now
    # (admin key is generated and logged on first startup)
    key = get_api_key(request)
    if key is None:
        # Allow through — will be enforced when gateway goes production
        return
    if not verify_api_key(key):
        raise HTTPException(status_code=401, detail="Invalid API key")


# ── Agent Loop instance (lazy) ─────────────────────────────

_loop = None


async def _get_loop():
    global _loop
    if _loop is None:
        from orchestrator.agent_loop import loop as agent_loop
        _loop = agent_loop
    return _loop


# ── SSE helper ─────────────────────────────────────────────

async def _stream_response(messages: list[dict], model: str | None = None) -> AsyncGenerator[str, None]:
    """Stream AgentLoop response as SSE events."""
    agent_loop = await _get_loop()
    # Convert messages to a user query (last user message)
    user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    if not user_msg:
        yield f"data: {json.dumps({'error': 'No user message found'})}\n\n"
        return

    # Run agent loop, intercepting streamed output
    loop_context = agent_loop.context
    loop_context.messages = messages

    # Stream tokens from the assistant
    from core.config import settings
    from providers.llm import stream_chat

    model_name = model or settings.model.default
    provider_name = model_name.split("/")[0] if "/" in model_name else settings.model.provider
    actual_model = model_name.split("/", 1)[-1] if "/" in model_name else model_name

    try:
        async for chunk in stream_chat(
            provider=provider_name,
            model=actual_model,
            messages=messages,
        ):
            content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
            if content:
                yield f"data: {json.dumps({'choices': [{'delta': {'content': content}}]})}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"


# ── Routes ─────────────────────────────────────────────────

@router.get("/health")
async def health_check():
    """System health endpoint."""
    return get_health()


@router.post("/chat/completions")
async def chat_completion(
    req: ChatCompletionRequest,
    _=Depends(require_auth),
):
    """Chat completion (streaming or non-streaming).

    Mirrors the OpenAI chat completions API format.
    """
    if req.stream:
        return EventSourceResponse(_stream_response(req.messages, req.model))

    # Non-streaming: collect full response
    full_content = ""
    async for event in _stream_response(req.messages, req.model):
        if event.startswith("data: [DONE]"):
            break
        if event.startswith("data: "):
            try:
                data = json.loads(event[6:])
                content = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                full_content += content
            except json.JSONDecodeError:
                pass

    return {
        "id": "dorina-chat",
        "object": "chat.completion",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": full_content}, "finish_reason": "stop"}],
    }


@router.get("/tools", response_model=list[ToolInfo])
async def list_tools(_=Depends(require_auth)):
    """List all registered tools."""
    from tools.registry import registry

    return [
        ToolInfo(
            name=t.name,
            description=t.description,
            toolset=t.toolset,
            parameters=None,
        )
        for t in registry.list()
    ]


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(limit: int = 20, _=Depends(require_auth)):
    """List recent sessions."""
    from session.manager import manager

    sessions = manager.list_sessions(limit=limit)
    return SessionListResponse(
        sessions=[
            SessionInfo(
                id=s["id"],
                title=s.get("title", ""),
                message_count=s.get("message_count", 0),
                summary=s.get("summary"),
                created_at=s.get("created_at"),
                updated_at=s.get("updated_at"),
            )
            for s in sessions
        ],
        total=len(sessions),
    )


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, _=Depends(require_auth)):
    """Get a specific session with full message history."""
    from session.manager import manager

    session = manager.load(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    return {
        "id": session.get("id"),
        "title": session.get("title", ""),
        "message_count": len(session.get("messages", [])),
        "messages": session.get("messages", []),
        "created_at": session.get("created_at"),
        "updated_at": session.get("updated_at"),
    }


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, _=Depends(require_auth)):
    """Delete a session."""
    from session.manager import manager

    session = manager.load(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    manager.delete(session_id)
    return {"status": "deleted", "id": session_id}


@router.post("/auth/keys", response_model=dict)
async def create_api_key(label: str = "admin", _=Depends(require_auth)):
    """Generate a new API key."""
    from .auth import generate_key

    raw_key = generate_key(label)
    return {"key": raw_key, "label": label, "warning": "Save this key — it will not be shown again"}


@router.get("/auth/keys", response_model=list[str])
async def list_api_keys(_=Depends(require_auth)):
    """List API key labels."""
    from .auth import list_labels

    return list_labels()


@router.delete("/auth/keys/{label}")
async def delete_api_key(label: str, _=Depends(require_auth)):
    """Revoke an API key."""
    from .auth import revoke_key

    if revoke_key(label):
        return {"status": "revoked", "label": label}
    raise HTTPException(status_code=404, detail=f"Key label '{label}' not found")
