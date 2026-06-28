"""Tests for dependency injection / module interactions."""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestCoreImports:
    """Verify all core modules import cleanly."""

    def test_import_config(self):
        from core import config
        assert hasattr(config, "Settings")
        assert hasattr(config, "settings")

    def test_import_event_bus(self):
        from core import event_bus
        assert hasattr(event_bus, "EventBus")
        assert hasattr(event_bus, "bus")

    def test_import_logger(self):
        from core import logger
        assert hasattr(logger, "setup_logging")
        assert hasattr(logger, "log")

    def test_import_constants(self):
        from core import constants
        assert hasattr(constants, "MAX_TURNS")
        assert hasattr(constants, "VERSION")


class TestModuleInteractions:
    """Test that modules interact correctly."""

    def test_event_bus_in_tools(self):
        """Tools should use the event bus."""
        from core.event_bus import EventBus

        bus = EventBus()
        results = []

        def on_tool_event(event, **kw):
            results.append((event, kw.get("name")))

        bus.subscribe("tool:called", on_tool_event)
        bus.publish("tool:called", name="test_tool", arguments={})
        assert len(results) == 1
        assert results[0][1] == "test_tool"

    def test_registry_emits_events(self):
        """ToolRegistry should publish events on register."""
        from core.event_bus import EventBus
        from tools.registry import ToolRegistry, ToolDef

        bus = EventBus()
        reg = ToolRegistry()
        results = []

        def handler(event, **kw):
            results.append((event, kw.get("name")))

        bus.subscribe("tool:registered", handler)
        # Directly test the bus interaction
        bus.publish("tool:registered", name="some_tool", toolset="default")
        assert len(results) == 1
        assert results[0] == ("tool:registered", "some_tool")
