"""Core module tests."""

try:
    import pytest
except ImportError:
    pytest = None


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

    def test_secret_redaction(self):
        import logging
        from core.logger import RedactingFormatter
        fmt = RedactingFormatter("%(message)s")
        rec = logging.LogRecord("test", logging.INFO, "", 0, "API key is sk-12345678901234567890secret", (), None)
        formatted = fmt.format(rec)
        assert "12345678901234567890secret" not in formatted
        assert "sk-***REDACTED***" in formatted


class TestUtils:
    def test_safe_json_loads(self):
        from core.utils import safe_json_loads
        # Direct string JSON parse
        assert safe_json_loads('{"a": 1}') == {"a": 1}
        # Bad string JSON returns default
        assert safe_json_loads('not json', default=[]) == []
        # Long string JSON is not attempted as file path
        long_json = '{"data": "' + 'x' * 600 + '"}'
        assert safe_json_loads(long_json)["data"].startswith("x")
