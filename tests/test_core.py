"""Core modülü testleri."""

import pytest


class TestConstants:
    def test_version(self):
        from core.constants import VERSION, NAME
        assert VERSION == "1.0.0"
        assert NAME == "dorina-agent"

    def test_constants_values(self):
        from core.constants import MAX_TURNS, MAX_TOOL_CALLS_PER_TURN
        assert MAX_TURNS > 0
        assert MAX_TOOL_CALLS_PER_TURN > 0


class TestEventBus:
    def test_publish_subscribe(self):
        from core.event_bus import EventBus
        bus = EventBus()
        results = []

        def handler(event, **kw):
            results.append((event, kw.get("data")))

        bus.subscribe("test:event", handler)
        bus.publish("test:event", data=42)
        assert len(results) == 1
        assert results[0] == ("test:event", 42)

    def test_unsubscribe(self):
        from core.event_bus import EventBus
        bus = EventBus()
        results = []

        def handler(event, **kw):
            results.append(1)

        sid = bus.subscribe("test", handler)
        bus.unsubscribe("test", sid)
        bus.publish("test")
        assert len(results) == 0


class TestLogger:
    def test_logger_creation(self):
        from core.logger import setup_logging
        logger = setup_logging()
        assert logger.name == "dorina"
        assert logger.level > 0
