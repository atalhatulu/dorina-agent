"""Runtime registry — the live state backbone for the Agent Workspace UI.

Listens to Dorina's event bus (`tool:*`, task/worker/cron) and exposes:

    snapshot()            → full current state (REST /api/runtime)
    subscribe(ws) / ...   → push deltas to connected browser(s) over /ws/events

This is the bridge the design report (Web UI v2) calls for: the UI renders
live Agent Activity, Execution Trace and Runtime Status from these events
instead of displaying hardcoded placeholders.

Thread-safety: publish() may be called from tool worker threads, so all
state mutation is guarded with a lock. Broadcast just schedules asyncio
tasks on the server loop.
"""
from __future__ import annotations

import asyncio
import threading
import time
from collections import deque
from typing import Optional

from core.event_bus import bus
from core.logger import log

APP_NAME = "Dorina"
APP_VERSION = "0.1.0"

# ── In-memory trace ledger (bounded FIFO) ─────────────────────────────
MAX_TOOL_TRACE = 200          # tool entries kept in the ledger
MAX_EVENT_LOG = 300           # recent bus events kept for /api/runtime?events=last


class _RuntimeState:
    def __init__(self):
        self._lock = threading.RLock()
        self.tool_trace: deque = deque(maxlen=MAX_TOOL_TRACE)
        self.event_log: deque = deque(maxlen=MAX_EVENT_LOG)
        self.workers: dict[str, dict] = {}      # worker role → live view
        self.tasks: dict[str, dict] = {}        # bg task id → view
        self.forks: dict[str, dict] = {}        # subagent fork id → view
        self.provider_routes: deque = deque(maxlen=50)
        self.session_label: str = "Web UI"
        self.model: str = ""
        self.provider: str = ""

    # ── mutation helpers (call under lock) ──────────────────────────
    def _push_event(self, ev_type: str, **data):
        self.event_log.append({
            "t": time.time(),
            "type": ev_type,
            **data,
        })

    def record_tool(self, status: str, **data):
        with self._lock:
            entry = {"status": status, "t": time.time(), **data}
            self.tool_trace.append(entry)
            self._push_event("tool." + status, name=data.get("name", "?"))

    def record_worker(self, role: str, status: str, **data):
        with self._lock:
            # Normalize lifecycle labels so the UI / runtime label can rely on
            # a closed set: started -> running, done -> completed.
            norm = {"started": "running", "done": "completed"}.get(status, status)
            existing = self.workers.get(role) or {
                "role": role, "started_at": time.time(),
            }
            existing.update({"status": norm, "t": time.time(), **data})
            if norm in ("completed", "failed"):
                existing["ended_at"] = time.time()
            self.workers[role] = existing
            self._push_event("worker." + norm, role=role)

    def record_task(self, task_id: str, status: str, **data):
        with self._lock:
            norm = {"started": "running", "done": "completed", "cancelled": "cancelled"}.get(status, status)
            existing = self.tasks.get(task_id) or {
                "id": task_id, "started_at": time.time(),
            }
            existing.update({"status": norm, "t": time.time(), **data})
            if norm in ("completed", "failed", "cancelled"):
                existing["ended_at"] = time.time()
            self.tasks[task_id] = existing
            self._push_event("task." + norm, id=task_id, name=data.get("name", "?"))

    def record_fork(self, fork_id: str, status: str, **data):
        with self._lock:
            norm = {"started": "running", "done": "completed", "error": "failed"}.get(status, status)
            self.forks[fork_id] = {"id": fork_id, "status": norm, "t": time.time(), **data}
            self._push_event("worker." + norm, role="subagent", fork_id=fork_id)

    def record_route(self, provider, model):
        with self._lock:
            self.provider_routes.append({"t": time.time(), "provider": provider, "model": model})
            self.model = model or self.model
            self.provider = provider or self.provider
            self._push_event("provider.selected", provider=provider, model=model)

    def bound_state(self) -> dict:
        """Thread-safe deep-ish snapshot of the aggregate (head only)."""
        with self._lock:
            return {
                "model": self.model,
                "provider": self.provider,
                "session": self.session_label,
                "workers": list(self.workers.values()),
                "tasks": list(self.tasks.values())[-40:],
                "forks": list(self.forks.values()),
                "tool_trace": list(self.tool_trace)[-60:],
                "provider_routes": list(self.provider_routes)[-20:],
            }


_state = _RuntimeState()


# ── Broadcast hub ─────────────────────────────────────────────────────

class _Broadcaster:
    def __init__(self):
        self._clients: set = set()
        self._lock = threading.Lock()

    def add(self, ws):
        with self._lock:
            self._clients.add(ws)

    def remove(self, ws):
        with self._lock:
            self._clients.discard(ws)

    def count(self) -> int:
        with self._lock:
            return len(self._clients)

    def broadcast(self, payload: dict):
        """Schedule a send to every connected /ws/events client. Never raises."""
        if not payload:
            return
        with self._lock:
            clients = list(self._clients)
        if not clients:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        for ws in clients:
            try:
                loop.create_task(self._safe_send(ws, payload))
            except Exception:  # noqa: BLE001
                pass

    async def _safe_send(self, ws, payload: dict):
        try:
            await ws.send_json(payload)
        except Exception:  # noqa: BLE001 — dead socket
            self.remove(ws)


_broadcast = _Broadcaster()

# Broadcast bus events to subscribers so the UI sees live activity. The
# bus handler runs in whichever thread published the event; we just forward
# a compact slice to the broadcaster which marshals it onto the IO loop.
_EVENT_WHITELIST = {
    "tool.executing", "tool.called", "tool.completed", "tool.error",
    "tool.aborted", "provider.selected",
}


def _on_bus_event(event, **data):
    _broadcast.broadcast({"type": "bus", "event": event, "data": data})


# ── Public API ────────────────────────────────────────────────────────

def snapshot():
    """Return full current runtime state (REST)."""
    base = _state.bound_state()
    base.update({
        "app": APP_NAME,
        "version": APP_VERSION,
        "watchers": _broadcast.count(),
        "runtime_status": _runtime_label(base),
    })
    return base


def bound_state() -> dict:
    """Expose the internal aggregate state (no envelope/watcher metadata)."""
    return _state.bound_state()


def app_name() -> str:
    return APP_NAME


def telegram_status() -> str:
    """Best-effort Telegram channel status."""
    try:
        from channels.telegram import telegram_bot  # type: ignore[import-not-found]
        active = getattr(telegram_bot, "active", False) or bool(getattr(telegram_bot, "_updater", None))
        return "connected" if active else "idle"
    except Exception:  # noqa: BLE001
        # Fall back to config-level token detection (never raise).
        try:
            from core.config import settings  # type: ignore[import-not-found]
            tok = getattr(getattr(settings, "telegram", None), "token", None) or getattr(settings, "telegram_token", None)
            return "connected" if tok else "not_configured"
        except Exception:
            return "not_configured"


def _runtime_label(state: dict) -> dict:
    running = [w for w in state.get("workers", []) if w.get("status") in ("running", "pending", "waiting")]
    workers = len(running)
    if workers:
        return {"label": f"RUNNING · {workers} WORKER(S)", "level": "running"}
    if state.get("forks"):
        return {"label": "RUNNING · SUBAGENT", "level": "running"}
    return {"label": "IDLE", "level": "idle"}


def subscribe(ws):
    _broadcast.add(ws)
    # Send the starting snapshot immediately so the UI can paint state.
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(ws.send_json({"type": "snapshot", "data": snapshot()}))
    except Exception:  # noqa: BLE001
        pass


def unsubscribe(ws):
    _broadcast.remove(ws)


_BUS_HOOKS_INSTALLED = False


def install_bus_hooks():
    """Register this module as an event bus subscriber. Idempotent."""
    global _BUS_HOOKS_INSTALLED
    if _BUS_HOOKS_INSTALLED:
        return
    _BUS_HOOKS_INSTALLED = True
    # Record tool trace entries + broadcast live tool activity.
    # NOTE: event names use COLON (`tool:called`) — executed in tools/executor.py.
    for ev in ("tool:executing", "tool:called", "tool:completed", "tool:error",
               "tool:aborted", "provider:selected"):
        bus.subscribe(ev, _on_bus_event)
    bus.subscribe("tool:called", _tool_called)
    bus.subscribe("tool:completed", _tool_completed)
    bus.subscribe("tool:error", _tool_error)
    bus.subscribe("tool:aborted", _tool_aborted)
    bus.subscribe("provider:selected", _on_provider)


def _tool_called(name, arguments=None, **kw):
    _state.record_tool("running", name=name, args=str(arguments or {})[:200])


def _tool_completed(name, result=None, **kw):
    _state.record_tool("completed", name=name, result=(str(result or ""))[:300])


def _tool_error(name, error=None, **kw):
    _state.record_tool("failed", name=name, error=str(error or "")[:300])


def _tool_aborted(name, reason="", **kw):
    _state.record_tool("aborted", name=name, reason=str(reason))


def _on_provider(provider=None, model=None, **kw):
    if provider:
        _state.record_route(provider, model)


# ── Worker/task bridge for crew.py + task_manager.py ─────────────────

def worker_event(role: str, status: str, **data):
    """Called by crew.py run_member to feed live worker state."""
    _state.record_worker(role, status, **data)
    _broadcast.broadcast({"type": "worker", "event": f"worker.{status}", "role": role, "data": data})


def fork_event(fork_id: str, status: str, **data):
    _state.record_fork(fork_id, status, **data)
    _broadcast.broadcast({"type": "worker", "event": f"worker.{status}", "fork_id": fork_id, "data": data})


def task_event(task_id: str, status: str, **data):
    """Task lifecycle hook — task_manager calls this on start/completion."""
    _state.record_task(task_id, status, **data)
    _broadcast.broadcast({"type": "task", "event": f"task.{status}", "id": task_id, "data": data})


# ── Session label ────────────────────────────────────────────────────

def set_session(sid: str):
    _state.session_label = sid or "Web UI"
