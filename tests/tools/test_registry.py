"""Tests for tools/registry.py"""
import pytest
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestToolDef:
    def test_tool_def_creation(self):
        from tools.registry import ToolDef

        def handler():
            pass

        t = ToolDef(
            name="my_tool",
            description="does something",
            parameters={"type": "object", "properties": {}},
            handler=handler,
        )
        assert t.name == "my_tool"
        assert t.toolset == "default"
        assert t.requires_env == []
        assert t.is_async is False
        assert t.check_fn is None

    def test_tool_def_custom_toolset(self):
        from tools.registry import ToolDef

        def handler():
            pass

        t = ToolDef(
            name="custom_tool",
            description="custom",
            parameters={},
            handler=handler,
            toolset="tasks",
            requires_env=["OPENAI_KEY"],
        )
        assert t.toolset == "tasks"
        assert t.requires_env == ["OPENAI_KEY"]


class TestToolRegistry:
    def test_register_and_get(self, fresh_registry):
        from tools.registry import ToolDef

        def handler():
            return "ok"

        tool = ToolDef(name="test_tool", description="test", parameters={}, handler=handler)
        fresh_registry.register(tool)
        assert fresh_registry.count() == 1
        assert fresh_registry.get("test_tool") is not None
        assert fresh_registry.get("nonexistent") is None

    def test_unregister(self, fresh_registry):
        from tools.registry import ToolDef

        def handler():
            pass

        t = ToolDef(name="temp", description="temp", parameters={}, handler=handler)
        fresh_registry.register(t)
        assert fresh_registry.count() == 1
        fresh_registry.unregister("temp")
        assert fresh_registry.count() == 0
        assert fresh_registry.get("temp") is None

    def test_list_by_toolset(self, fresh_registry):
        from tools.registry import ToolDef

        def handler():
            pass

        fresh_registry.register(ToolDef(name="a", description="a", parameters={}, handler=handler, toolset="default"))
        fresh_registry.register(ToolDef(name="b", description="b", parameters={}, handler=handler, toolset="tasks"))
        fresh_registry.register(ToolDef(name="c", description="c", parameters={}, handler=handler, toolset="tasks"))

        default_tools = fresh_registry.list(toolset="default")
        tasks_tools = fresh_registry.list(toolset="tasks")
        assert len(default_tools) == 1
        assert len(tasks_tools) == 2
        assert len(fresh_registry.list()) == 3

    def test_available_tools_with_check_fn(self, fresh_registry):
        from tools.registry import ToolDef

        def handler():
            pass

        def check_available():
            return False

        def check_unavailable():
            return True

        fresh_registry.register(ToolDef(name="avail", description="", parameters={}, handler=handler, check_fn=check_unavailable))
        fresh_registry.register(ToolDef(name="unavail", description="", parameters={}, handler=handler, check_fn=check_available))
        fresh_registry.register(ToolDef(name="no_check", description="", parameters={}, handler=handler))

        available = fresh_registry.available_tools()
        assert "avail" in available
        assert "unavail" not in available
        assert "no_check" in available

    def test_schemas_format(self, fresh_registry):
        from tools.registry import ToolDef

        def handler():
            return "ok"

        tool = ToolDef(
            name="test", description="desc",
            parameters={"type": "object", "properties": {"x": {"type": "string"}}},
            handler=handler,
        )
        fresh_registry.register(tool)
        schemas = fresh_registry.schemas()
        assert len(schemas) == 1
        assert schemas[0]["type"] == "function"
        schema_func = schemas[0]["function"]
        assert schema_func["name"] == "test"
        assert schema_func["description"] == "desc"
        assert "parameters" in schema_func

    def test_hook_management(self, fresh_registry):
        def pre_hook(tool_name, arguments):
            return True

        fresh_registry.clear_hooks()
        fresh_registry.register_hook("pre_execution", pre_hook)
        hooks = fresh_registry.list_hooks()
        assert "pre_execution" in hooks
        assert len(hooks["pre_execution"]) >= 1

        count = fresh_registry.hook_count()
        assert count >= 1

        fresh_registry.clear_hooks()
        hooks = fresh_registry.list_hooks()
        assert len(hooks["pre_execution"]) == 0

    def test_register_twice_overwrites(self, fresh_registry):
        from tools.registry import ToolDef

        def handler1():
            return "first"

        def handler2():
            return "second"

        fresh_registry.register(ToolDef(name="dup", description="first", parameters={}, handler=handler1))
        fresh_registry.register(ToolDef(name="dup", description="second", parameters={}, handler=handler2))
        assert fresh_registry.count() == 1
        assert fresh_registry.get("dup").description == "second"
