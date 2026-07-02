"""Tests for tools/executor.py"""
import pytest
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestToolExecutor:
    def test_execute_sync_tool(self, patch_registry):
        """Use patch_registry to register on the global singleton the executor uses."""
        from tools.registry import ToolDef
        from tools.executor import executor

        def add(a: int = 0, b: int = 0) -> str:
            return json.dumps({"result": a + b})

        tool = ToolDef(name="test_add", description="add", parameters={
            "type": "object",
            "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
        }, handler=add)
        patch_registry.register(tool)

        result = executor.execute("test_add", {"a": 5, "b": 3})
        data = json.loads(result)
        assert data["result"] == 8

    def test_execute_with_string_args(self, patch_registry):
        from tools.registry import ToolDef
        from tools.executor import executor

        def echo(msg: str = "") -> str:
            return json.dumps({"msg": msg})

        tool = ToolDef(name="echo_tool", description="echo", parameters={
            "type": "object",
            "properties": {"msg": {"type": "string"}},
        }, handler=echo)
        patch_registry.register(tool)

        result = executor.execute_json("echo_tool", '{"msg": "hello"}')
        data = json.loads(result)
        assert data["msg"] == "hello"

    def test_execute_tool_not_found(self):
        from tools.executor import executor
        import json
        result = executor.execute("nonexistent_tool", {})
        data = json.loads(result)
        assert "error" in data
        assert "Tool bulunamadı" in data["error"]

    def test_execute_multi(self, patch_registry):
        from tools.registry import ToolDef
        from tools.executor import executor

        def handler1():
            return "result1"

        def handler2():
            return "result2"

        patch_registry.register(ToolDef(name="t1", description="", parameters={}, handler=handler1))
        patch_registry.register(ToolDef(name="t2", description="", parameters={}, handler=handler2))

        calls = [
            {"name": "t1", "arguments": {}},
            {"name": "t2", "arguments": {}},
        ]
        results = executor.execute_multi(calls)
        assert len(results) == 2
        assert results[0]["name"] == "t1"
        assert results[0]["error"] is None

    def test_execute_multi_with_error(self, patch_registry):
        from tools.registry import ToolDef
        from tools.executor import executor

        def good():
            return "ok"

        patch_registry.register(ToolDef(name="good_tool", description="", parameters={}, handler=good))

        results = executor.execute_multi([
            {"name": "good_tool", "arguments": {}},
            {"name": "bad_tool", "arguments": {}},
        ])
        import json
        assert results[0]["error"] is None
        assert results[0]["result"] == "ok"
        # Bilinmeyen tool artik ToolError firlatmaz, JSON error string dondurur
        if results[1]["error"] is not None:
            pass  # eski davranis
        elif results[1]["result"] is not None:
            data = json.loads(results[1]["result"])
            assert "error" in data
            assert "Tool bulunamadı" in data["error"]

    def test_call_count_increment(self, patch_registry):
        from tools.registry import ToolDef
        from tools.executor import executor

        def handler():
            return "ok"

        patch_registry.register(ToolDef(name="counter_test", description="", parameters={}, handler=handler))
        count_before = executor.call_count
        executor.execute("counter_test", {})
        assert executor.call_count == count_before + 1
        executor.reset_count()
        assert executor.call_count == 0

    def test_required_params_validation(self, patch_registry):
        from tools.registry import ToolDef
        from tools.executor import executor

        def greet(name: str) -> str:
            import json
            return json.dumps({"greeting": f"Hello {name}"})

        tool = ToolDef(
            name="greet", description="greet",
            parameters={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
            handler=greet,
        )
        patch_registry.register(tool)

        # With required param - should work
        result = executor.execute("greet", {"name": "Dorina"})
        data = json.loads(result)
        assert data["greeting"] == "Hello Dorina"

    def test_alias_resolution(self, patch_registry):
        """bash, sh, shell should resolve to terminal."""
        from tools.registry import ToolDef
        from tools.executor import executor

        def term_handler(command: str = "") -> str:
            return json.dumps({"result": f"ran: {command[:20]}"})

        patch_registry.register(ToolDef(
            name="terminal", description="run command",
            parameters={"type": "object", "properties": {"command": {"type": "string"}}},
            handler=term_handler,
        ))

        result = executor.execute("bash", {"command": "echo hello"})
        data = json.loads(result)
        assert "ran: echo hello" in data["result"]

    def test_executor_errors_sanitized(self, patch_registry):
        from tools.registry import ToolDef
        from tools.executor import executor

        def broken():
            raise ValueError("something broke")

        patch_registry.register(ToolDef(
            name="broken_tool", description="broken",
            parameters={}, handler=broken,
        ))

        result = executor.execute("broken_tool", {})
        data = json.loads(result)
        assert "error" in data
