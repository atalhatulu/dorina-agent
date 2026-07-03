"""Event-driven communication system.

Modules don't call each other directly — they fire events.
E.g., when a tool is called → "tool:called" event → log, memory, stats listen.
"""

from typing import Callable, Any
from collections import defaultdict
import uuid
from core.logger import log


class EventBus:
    """Publish/Subscribe event bus."""

    def __init__(self):
        self._subscribers: dict[str, list[tuple[str, Callable]]] = defaultdict(list)

    def subscribe(self, event: str, callback: Callable, subscriber_id: str | None = None) -> str:
        """Subscribe to an event. Returns an ID to unsubscribe with."""
        sid = subscriber_id or str(uuid.uuid4())[:8]
        self._subscribers[event].append((sid, callback))
        return sid

    def unsubscribe(self, event: str, subscriber_id: str):
        """Unsubscribe from an event."""
        self._subscribers[event] = [
            (sid, cb) for sid, cb in self._subscribers[event] if sid != subscriber_id
        ]

    def publish(self, event: str, **data: Any):
        """Fire an event. Notify all subscribers."""
        for sid, callback in self._subscribers.get(event, []):
            try:
                callback(event=event, **data)
            except Exception as e:
                log.error(f"Event handler error [{sid}]: {e}")

    def clear(self):
        """Clear all subscriptions."""
        self._subscribers.clear()


# Global event bus
bus = EventBus()
