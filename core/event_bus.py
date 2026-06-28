"""Event-driven haberleşme sistemi.

Modüller birbirini doğrudan çağırmaz, event fırlatır.
Örn: tool çağrılınca → "tool:called" event'i → log, memory, istatistik dinler.
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
        """Event'e abone ol. Dönen ID ile aboneliği kaldırabilirsin."""
        sid = subscriber_id or str(uuid.uuid4())[:8]
        self._subscribers[event].append((sid, callback))
        return sid

    def unsubscribe(self, event: str, subscriber_id: str):
        """Aboneliği kaldır."""
        self._subscribers[event] = [
            (sid, cb) for sid, cb in self._subscribers[event] if sid != subscriber_id
        ]

    def publish(self, event: str, **data: Any):
        """Event fırlat. Tüm abonelere haber ver."""
        for sid, callback in self._subscribers.get(event, []):
            try:
                callback(event=event, **data)
            except Exception as e:
                log.error(f"Event handler hatası [{sid}]: {e}")

    def clear(self):
        """Tüm abonelikleri temizle."""
        self._subscribers.clear()


# Global event bus
bus = EventBus()
