"""
Dorina Web Dashboard — FastAPI + WebSocket.
Local only, no cloud. Serves on http://localhost:5792
"""
from __future__ import annotations
import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

_proj_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_proj_root))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
import uvicorn

from core.logger import log
from core.constants import NAME, VERSION
from session.manager import manager as session_manager

# Register all tools at startup
import tools.builtin  # noqa: F401 — @register_tool decorators execute here

app = FastAPI(title=f"{NAME} Dashboard", version=VERSION)

static_dir = Path(__file__).parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def index():
    html = (static_dir / "index.html").read_text(encoding="utf-8")
    return Response(content=html, media_type="text/html",
                    headers={"Cache-Control": "no-cache, no-store, must-revalidate",
                             "Pragma": "no-cache", "Expires": "0"})


# ── REST API ─────────────────────────────────────────────────

@app.get("/api/status")
async def api_status():
    from core.config import settings
    sessions = session_manager.list_sessions(limit=100)
    active_sid = getattr(session_manager, "current_id", None) or ""
    active_session = None
    if active_sid:
        active_session = session_manager.load(active_sid)
    return {
        "name": NAME,
        "version": VERSION,
        "model": settings.model.default,
        "provider": settings.model.provider,
        "sessions": {
            "total": len(sessions),
            "active_id": active_sid,
            "active_title": (active_session or {}).get("title", "") if active_session else "",
        },
        "modes": get_active_modes(),
    }


def get_active_modes() -> list[str]:
    try:
        from core.mode_manager import modes
        return modes.active
    except (ImportError, AttributeError):
        return []


@app.get("/api/sessions")
async def api_sessions(limit: int = 50):
    sessions = session_manager.list_sessions(limit=limit)
    return {"sessions": sessions}


@app.delete("/api/sessions/{session_id}")
async def api_delete_session(session_id: str):
    ok = session_manager.delete(session_id)
    if not ok:
        raise HTTPException(404, "Session not found")
    return {"ok": True}


@app.post("/api/sessions")
async def api_create_session():
    sid = session_manager.create(title="Web Session")
    return {"session_id": sid, "title": "Web Session"}


@app.get("/api/sessions/{session_id}")
async def api_get_session(session_id: str):
    session = session_manager.load(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return session


@app.post("/api/chat")
async def api_chat(query: str, session_id: Optional[str] = None):
    from orchestrator.experimental_loop import loop_v2 as loop
    if not session_id:
        session_id = session_manager.current_id or session_manager.create(title="Web Chat")
    session_manager.current_id = session_id
    result = await loop.process(query)
    return {"response": result, "session_id": session_id}


# ── WebSocket ────────────────────────────────────────────────

def _extract_tool_calls(messages: list[dict]) -> list[dict]:
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
                        "args": fn.get("arguments", "{}")[:200],
                    })
        elif role == "tool":
            steps.append({
                "type": "tool_result",
                "name": msg.get("name", "?"),
                "content_preview": str(msg.get("content", ""))[:100],
            })
    return steps


@app.websocket("/ws/chat")
async def websocket_chat(ws: WebSocket):
    await ws.accept()
    from orchestrator.experimental_loop import loop_v2 as loop
    from ui.status_bar import status

    session_id = session_manager.current_id or session_manager.create(title="Web Chat")
    session_manager.current_id = session_id

    await ws.send_json({"type": "session", "session_id": session_id})

    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            query = msg.get("query", "").strip()
            if not query:
                continue

            await ws.send_json({"type": "user", "content": query})

            tokens_before = status.tokens_in + status.tokens_out
            cost_before = status.cost

            try:
                async def _on_step(step_type: str, name: str, data: dict):
                    try:
                        await ws.send_json({
                            "type": "step",
                            "step": step_type,
                            "name": name,
                            "data": data,
                        })
                    except Exception:
                        pass

                result = await loop.process(query, on_step=_on_step)
                final_text = str(result) if result else ""

                tokens_after = status.tokens_in + status.tokens_out
                usage = {
                    "prompt_tokens": max(0, status.tokens_in - (tokens_before - status.tokens_out)),
                    "completion_tokens": max(0, status.tokens_out - (tokens_before - status.tokens_in)),
                    "total_tokens": max(0, tokens_after - tokens_before),
                    "cost": max(0, status.cost - cost_before),
                    "total_in": status.tokens_in,
                    "total_out": status.tokens_out,
                    "total_cost": status.cost,
                }

                tool_steps = _extract_tool_calls(loop.context.get_messages())

                await ws.send_json({
                    "type": "assistant",
                    "content": final_text,
                    "tools": tool_steps[-10:] if tool_steps else [],
                    "usage": usage,
                    "done": True,
                })
            except Exception as e:
                await ws.send_json({"type": "error", "content": str(e), "done": True})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.error(f"WebSocket error: {e}")


def main():
    port = 5792
    print(f"  {NAME} Dashboard → http://localhost:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
