"""Tests for core/event_bus.py"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestEventBus:
    def test_publish_subscribe(self, fresh_event_bus):
        bus = fresh_event_bus
        results = []

        def handler(event, **kw):
            results.append((event, kw.get("data")))

        sid = bus.subscribe("test:event", handler)
        bus.publish("test:event", data=42)
        assert len(results) == 1
        assert results[0] == ("test:event", 42)

    def test_unsubscribe(self, fresh_event_bus):
        bus = fresh_event_bus
        results = []

        def handler(event, **kw):
            results.append(1)

        sid = bus.subscribe("test:unsub", handler)
        bus.unsubscribe("test:unsub", sid)
        bus.publish("test:unsub")
        assert len(results) == 0

    def test_multiple_subscribers(self, fresh_event_bus):
        bus = fresh_event_bus
        results = []

        def handler1(event, **kw):
            results.append("h1")

        def handler2(event, **kw):
            results.append("h2")

        bus.subscribe("multi", handler1)
        bus.subscribe("multi", handler2)
        bus.publish("multi")
        assert len(results) == 2
        assert "h1" in results
        assert "h2" in results

    def test_event_data_passthrough(self, fresh_event_bus):
        bus = fresh_event_bus
        captured = {}

        def handler(event, **kw):
            captured.update(kw)

        bus.subscribe("data_test", handler)
        bus.publish("data_test", name="test_tool", value=100, status="ok")
        assert captured.get("name") == "test_tool"
        assert captured.get("value") == 100
        assert captured.get("status") == "ok"

    def test_clear_all_subscriptions(self, fresh_event_bus):
        bus = fresh_event_bus
        results = []

        def handler(event, **kw):
            results.append(1)

        bus.subscribe("a", handler)
        bus.subscribe("b", handler)
        bus.clear()
        bus.publish("a")
        bus.publish("b")
        assert len(results) == 0

    def test_error_handler_doesnt_block(self, fresh_event_bus):
        """Error in one handler shouldn't block others."""
        bus = fresh_event_bus
        results = []

        def bad_handler(event, **kw):
            raise ValueError("oops")

        def good_handler(event, **kw):
            results.append("ok")

        bus.subscribe("err", bad_handler)
        bus.subscribe("err", good_handler)
        bus.publish("err")
        assert len(results) == 1
        assert results[0] == "ok"

    def test_subscriber_id_generation(self, fresh_event_bus):
        bus = fresh_event_bus

        def handler(event, **kw):
            pass

        sid1 = bus.subscribe("e1", handler)
        sid2 = bus.subscribe("e2", handler, subscriber_id="my_custom_id")
        assert len(sid1) == 8
        assert sid2 == "my_custom_id"

    def test_different_events_isolated(self, fresh_event_bus):
        bus = fresh_event_bus
        results_a = []
        results_b = []

        def handler_a(event, **kw):
            results_a.append(1)

        def handler_b(event, **kw):
            results_b.append(1)

        bus.subscribe("evt_a", handler_a)
        bus.subscribe("evt_b", handler_b)
        bus.publish("evt_a")
        bus.publish("evt_a")
        assert len(results_a) == 2
        assert len(results_b) == 0
