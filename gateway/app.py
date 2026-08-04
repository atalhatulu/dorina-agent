"""
Dorina Web Dashboard — FastAPI + WebSocket.
Local only, no cloud. Serves on http://localhost:5792
"""
from __future__ import annotations
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Optional

_proj_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_proj_root))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, Query, Depends
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
import uvicorn

from core.logger import log
from core.constants import NAME, VERSION
from session.manager import manager as session_manager
from gateway.auth import verify_token, is_auth_enabled

# Register all tools at startup
import tools.builtin  # noqa: F401

app = FastAPI(title=f"{NAME} Dashboard", version=VERSION)

from gateway.a2a import a2a_router
app.include_router(a2a_router)

static_dir = Path(__file__).parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ── Auth helpers ────────────────────────────────────────

async def _check_auth(request: Request):
    """REST dependency: 401 if auth enabled and token missing/invalid."""
    if not is_auth_enabled():
        return
    token = request.headers.get("X-Dashboard-Token", "")
    if not verify_token(token):
        raise HTTPException(401, "Unauthorized — X-Dashboard-Token header gerekli")


# ── Helpers ──────────────────────────────────────────────

def _get_loop():
    from orchestrator.experimental_loop import loop_v2
    return loop_v2


def _get_modes() -> list[str]:
    try:
        from core.mode_manager import modes
        return modes.active
    except (ImportError, AttributeError):
        return []


# ── HTML ─────────────────────────────────────────────────

@app.get("/")
async def index():
    html = (static_dir / "index.html").read_text(encoding="utf-8")
    return Response(
        content=html, media_type="text/html",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache", "Expires": "0",
        },
    )


# ── REST API ─────────────────────────────────────────────

@app.get("/api/status", dependencies=[Depends(_check_auth)])
async def api_status():
    from core.config import settings
    sessions = session_manager.list_sessions(limit=100)
    active_sid = getattr(session_manager, "current_id", None) or ""
    return {
        "name": NAME,
        "version": VERSION,
        "model": settings.model.default,
        "provider": settings.model.provider,
        "sessions": {"total": len(sessions)},
        "modes": _get_modes(),
    }


@app.get("/api/sessions", dependencies=[Depends(_check_auth)])
async def api_sessions(limit: int = 50):
    sessions = session_manager.list_sessions(limit=limit)
    return {"sessions": sessions}


@app.get("/api/providers", dependencies=[Depends(_check_auth)])
async def api_providers():
    """List all providers with models, key status, and current selection."""
    from providers.keys import keys as key_mgr
    from core.config import settings
    providers = []
    for pid, name in key_mgr.list_providers():
        info = key_mgr.get_provider_info(pid) or {}
        providers.append({
            "id": pid,
            "name": name,
            "models": key_mgr.get_models(pid) or [],
            "needs_key": bool(info.get("needs_key", True)),
            "has_key": key_mgr.has_key(pid),
        })
    return {
        "providers": providers,
        "current": {
            "provider": settings.model.provider,
            "model": settings.model.default,
        },
    }


@app.post("/api/setup", dependencies=[Depends(_check_auth)])
async def api_setup(data: dict):
    """Set provider + model (optionally an API key). Persists to config.yaml + providers.json."""
    from providers.keys import keys as key_mgr
    from core.config import settings
    provider = (data.get("provider") or "").strip()
    model = (data.get("model") or "").strip()
    api_key = (data.get("api_key") or "").strip()
    if not provider:
        raise HTTPException(400, "provider gerekli")
    info = key_mgr.get_provider_info(provider)
    if info is None:
        raise HTTPException(404, f"Bilinmeyen sağlayıcı: {provider}")
    if api_key and info.get("needs_key", True):
        key_mgr.save_key(provider, api_key)
    key_mgr.switch_to(provider, model or None)
    return {"ok": True, "provider": provider, "model": settings.model.default}


@app.post("/api/sessions", dependencies=[Depends(_check_auth)])
async def api_create_session():
    sid = session_manager.create(title="Web Session")
    return {"session_id": sid, "title": "Web Session"}


@app.get("/api/sessions/{session_id}", dependencies=[Depends(_check_auth)])
async def api_get_session(session_id: str):
    session = session_manager.load(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return session


@app.delete("/api/sessions/{session_id}", dependencies=[Depends(_check_auth)])
async def api_delete_session(session_id: str):
    ok = session_manager.delete(session_id)
    if not ok:
        raise HTTPException(404, "Session not found")
    return {"ok": True}


@app.post("/api/sessions/{session_id}/rename", dependencies=[Depends(_check_auth)])
async def api_rename_session(session_id: str, data: dict):
    title = data.get("title", "")
    if not title:
        raise HTTPException(400, "Title is required")
    session_manager.rename(session_id, title)
    return {"ok": True}


@app.get("/api/sessions/search/{query}", dependencies=[Depends(_check_auth)])
async def api_search_sessions(query: str):
    results = session_manager.search(query)
    return {"results": results}


# ── WebSocket ────────────────────────────────────────────

class ConnectionState:
    """Per-connection state for tracking tool steps and usage."""
    def __init__(self):
        self.session_id: str = ""
        self.tools_before: list = []
        self.tokens_before = 0
        self.cost_before = 0.0
        self.last_msg_time = 0.0
        self.msg_count = 0


# ── Rate limiting (per-connection, token-bucket style) ──
import time as _time

RATE_LIMIT = {
    "min_interval": 1.0,    # en az 1 sn arka arkaya mesaj
    "max_per_minute": 20,   # dakikada en fazla 20 mesaj
}

async def _check_rate_limit(state: ConnectionState) -> str | None:
    """Return error message if rate limit exceeded, else None."""
    now = _time.monotonic()
    if state.msg_count == 0:
        state.last_msg_time = now
        state.msg_count = 1
        return None
    dt = now - state.last_msg_time
    state.msg_count += 1
    # Sliding window: son 60 sn'de max_per_minute'ı aşma
    if state.msg_count > RATE_LIMIT["max_per_minute"] and dt < 60:
        return f"Rate limit: en fazla {RATE_LIMIT['max_per_minute']} mesaj/dakika. Lütfen biraz bekleyin."
    if dt < RATE_LIMIT["min_interval"]:
        return "Çok hızlı mesaj gönderiyorsun — lütfen 1 sn bekleyin."
    if dt > 60:
        state.msg_count = 1  # pencere sıfırla
    state.last_msg_time = now
    return None


async def _tool_step_callback(ws: WebSocket, state: ConnectionState, step_type: str, name: str, data: dict):
    """Stream tool steps and reasoning to the WebSocket in real-time."""
    try:
        # Reasoning content goes as a special step type
        if step_type == "reasoning":
            await ws.send_json({
                "type": "reasoning",
                "content": data.get("content", ""),
            })
        else:
            await ws.send_json({
                "type": "step",
                "step": step_type,
                "name": name,
                "data": data,
            })
    except Exception:
        pass


@app.websocket("/ws/chat")
async def websocket_chat(ws: WebSocket, token: str = Query("")):
    await ws.accept()
    # Auth check: token query param must match (if auth enabled)
    if not verify_token(token):
        await ws.send_json({"type": "error", "content": "Unauthorized — geçersiz token"})
        await ws.close(code=4401)
        return
    from orchestrator.experimental_loop import loop_v2 as loop
    from ui.status_bar import status

    state = ConnectionState()
    state.session_id = session_manager.current_id or session_manager.create(title="Web Chat")
    session_manager.current_id = state.session_id

    # Restore context from the session DB on reconnect (memory across restarts)
    _saved = session_manager.load(state.session_id)
    if _saved and _saved.get("messages"):
        loop.context.messages = [dict(m) for m in _saved["messages"]]
        loop.turn = max(1, sum(1 for m in _saved["messages"] if m.get("role") == "user"))
        loop._skills_injected = False

    await ws.send_json({"type": "session", "session_id": state.session_id, "title": "Web Session"})

    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)

            # ── Rate limit guard (except session mgmt commands) ──
            if msg.get("type") in (None, "query", "user"):
                rl_err = await _check_rate_limit(state)
                if rl_err:
                    await ws.send_json({"type": "error", "content": rl_err})
                    continue

            # ── Session management commands ──
            if msg.get("type") == "switch_session":
                sid = msg.get("session_id", "")
                session = session_manager.load(sid)
                if session:
                    session_manager.current_id = sid
                    state.session_id = sid
                    # Restore context from saved session — memory across sessions
                    saved_msgs = session.get("messages", [])
                    if saved_msgs:
                        loop.context.messages = [dict(m) for m in saved_msgs]
                        loop.turn = max(1, sum(1 for m in saved_msgs if m.get("role") == "user"))
                        loop._skills_injected = False
                    await ws.send_json({
                        "type": "session_loaded",
                        "session_id": sid,
                        "title": session.get("title", "Web Session"),
                        "messages": saved_msgs,
                    })
                continue

            if msg.get("type") == "new_session":
                sid = session_manager.create(title="Web Session")
                session_manager.current_id = sid
                state.session_id = sid
                # Fresh context for the new session
                loop.context.messages = []
                loop.turn = 0
                loop._skills_injected = False
                await ws.send_json({
                    "type": "session_loaded",
                    "session_id": sid,
                    "title": "Web Session",
                    "messages": [],
                })
                continue

            if msg.get("type") == "delete_session":
                sid = msg.get("session_id", "")
                session_manager.delete(sid)
                await ws.send_json({"type": "session_deleted", "session_id": sid})
                continue

            if msg.get("type") == "rename_session":
                sid = msg.get("session_id", "")
                title = msg.get("title", "")
                session_manager.rename(sid, title)
                await ws.send_json({"type": "session_renamed", "session_id": sid, "title": title})
                continue

            # ── Chat message ──
            query = msg.get("query", "").strip()
            if not query:
                continue

            # Set session
            req_session_id = msg.get("session_id", "")
            if req_session_id and req_session_id != state.session_id:
                session_manager.current_id = req_session_id
                state.session_id = req_session_id

            await ws.send_json({"type": "user", "content": query})

            state.tokens_before = status.tokens_in + status.tokens_out
            state.cost_before = status.cost
            state.tools_before = []

            try:
                # Create streaming callback
                async def _on_step(st, nm, dd):
                    await _tool_step_callback(ws, state, st, nm, dd)

                result = await loop.process(query, on_step=_on_step)
                final_text = str(result) if result else ""

                # Calculate usage — only count LAST LLM call's context size
                # (cumulative add inflates it due to tool loop iterations)
                last_prompt = status.get_last_prompt_tokens()
                last_completion = status.get_last_completion_tokens()
                cumulative_in = status.tokens_in
                cumulative_out = status.tokens_out
                usage = {
                    "prompt_tokens": last_prompt,
                    "completion_tokens": last_completion,
                    "total_tokens": last_prompt + last_completion,
                    "total_in": cumulative_in,
                    "total_out": cumulative_out,
                    "cumulative_tokens": max(0, cumulative_in + cumulative_out - state.tokens_before),
                    "cost": max(0, status.cost - state.cost_before),
                    "total_cost": status.cost,
                }

                # Extract tool steps from context
                tool_steps = _extract_tool_calls(loop.context.get_messages())

                await ws.send_json({
                    "type": "assistant",
                    "content": final_text,
                    "tools": tool_steps[-15:] if tool_steps else [],
                    "usage": usage,
                    "done": True,
                })

                # Auto-save
                session_manager.save(loop.context.get_messages())

            except Exception as e:
                await ws.send_json({"type": "error", "content": str(e), "done": True})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.error(f"WebSocket error: {e}")


def _extract_tool_calls(messages: list[dict]) -> list[dict]:
    """Extract tool call/result steps from message history."""
    steps = []
    for msg in messages:
        role = msg.get("role", "")
        if role == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                if isinstance(tc, dict):
                    fn = tc.get("function", {})
                    steps.append({
                        "type": "tool_call",
                        "name": fn.get("name", "?"),
                        "args": str(fn.get("arguments", "{}"))[:300],
                    })
        elif role == "tool":
            steps.append({
                "type": "tool_result",
                "name": msg.get("name", "?"),
                "content_preview": str(msg.get("content", ""))[:200],
                "tool_call_id": msg.get("tool_call_id", ""),
            })
    return steps


# ── Entry ────────────────────────────────────────────────

def main():
    port = 5792
    print(f"  {NAME} Dashboard → http://localhost:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
