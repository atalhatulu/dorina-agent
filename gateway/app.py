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

# Proje kokunu PYTHONPATH'e ekle
_proj_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_proj_root))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import uvicorn

from core.logger import log
from core.constants import NAME, VERSION
from session.manager import manager as session_manager

# ── FastAPI ──────────────────────────────────────────────────
app = FastAPI(title=f"{NAME} Dashboard", version=VERSION)

# ── Static files ─────────────────────────────────────────────
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def index():
    html = (static_dir / "index.html").read_text(encoding="utf-8")
    from fastapi.responses import HTMLResponse
    from fastapi import Response
    return Response(content=html, media_type="text/html",
                    headers={"Cache-Control": "no-cache, no-store, must-revalidate",
                             "Pragma": "no-cache", "Expires": "0"})


# ── REST API ─────────────────────────────────────────────────

@app.get("/api/status")
async def api_status():
    """System status: version, session count, uptime."""
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
    """List sessions."""
    sessions = session_manager.list_sessions(limit=limit)
    return {"sessions": sessions}


@app.delete("/api/sessions/{session_id}")
async def api_delete_session(session_id: str):
    """Delete a session."""
    ok = session_manager.delete(session_id)
    if not ok:
        raise HTTPException(404, "Session not found")
    return {"ok": True}


@app.post("/api/sessions")
async def api_create_session():
    """Create a new session."""
    sid = session_manager.create(title="Web Session")
    return {"session_id": sid, "title": "Web Session"}


@app.get("/api/sessions/{session_id}")
async def api_get_session(session_id: str):
    """Get session details with messages."""
    session = session_manager.load(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return session


@app.post("/api/chat")
async def api_chat(query: str, session_id: Optional[str] = None):
    """Send a message to agent (non-streaming)."""
    from orchestrator.experimental_loop import loop_v2 as loop

    if not session_id:
        session_id = session_manager.current_id or session_manager.create(title="Web Chat")

    # Set current session
    session_manager.current_id = session_id
    result = await loop.process(query)
    return {"response": result, "session_id": session_id}


# ── WebSocket ────────────────────────────────────────────────

@app.websocket("/ws/chat")
async def websocket_chat(ws: WebSocket):
    """Streaming chat via WebSocket."""
    await ws.accept()
    from orchestrator.experimental_loop import loop_v2 as loop

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

            # Run agent
            try:
                result = await loop.process(query)
                if result and isinstance(result, str):
                    await ws.send_json({"type": "assistant", "content": result, "done": True})
                else:
                    await ws.send_json({"type": "assistant", "content": str(result) if result else "", "done": True})
            except Exception as e:
                await ws.send_json({"type": "error", "content": str(e), "done": True})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.error(f"WebSocket error: {e}")


# ── Entry point ──────────────────────────────────────────────

def main():
    """Start the dashboard server."""
    port = 5792
    print(f"  {NAME} Dashboard → http://localhost:{port}")
    print(f"  (Ctrl+C to stop)")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
