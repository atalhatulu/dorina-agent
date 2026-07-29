"""Event-driven communication system.

Modules don't call each other directly — they fire events.
E.g., when a tool is called → "tool:called" event → log, memory, stats listen.
"""

from typing import Callable, Any
from collections import defaultdict
import uuid
import weakref
from core.logger import log


import inspect
import asyncio


class EventBus:
    """Publish/Subscribe event bus."""

    def __init__(self):
        self._subscribers: dict[str, list[tuple[str, Any]]] = defaultdict(list)

    def subscribe(self, event: str, callback: Callable, subscriber_id: str | None = None) -> str:
        """Subscribe to an event. Returns an ID to unsubscribe with."""
        sid = subscriber_id or str(uuid.uuid4())[:8]
        try:
            if hasattr(callback, "__self__"):
                ref = weakref.WeakMethod(callback)
            else:
                ref = callback
        except TypeError:
            ref = callback
        self._subscribers[event].append((sid, ref))
        return sid

    def unsubscribe(self, event: str, subscriber_id: str):
        """Unsubscribe from an event."""
        self._subscribers[event] = [
            (sid, ref) for sid, ref in self._subscribers[event] if sid != subscriber_id
        ]

    def publish(self, event: str, **data: Any):
        """Fire an event. Notify all subscribers."""
        dead = []
        for sid, ref in list(self._subscribers.get(event, [])):
            if isinstance(ref, (weakref.WeakMethod, weakref.ref)):
                callback = ref()
                if callback is None:
                    dead.append((sid, ref))
                    continue
            else:
                callback = ref

            try:
                res = callback(event=event, **data)
                if inspect.iscoroutine(res):
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(res)
                    except RuntimeError:
                        asyncio.run(res)
            except Exception as e:
                log.error(f"Event handler error [{sid}]: {e}")

        if dead:
            self._subscribers[event] = [
                (s, r) for s, r in self._subscribers[event] if (s, r) not in dead
            ]

    def clear(self):
        """Clear all subscriptions."""
        self._subscribers.clear()


# Global event bus
bus = EventBus()
