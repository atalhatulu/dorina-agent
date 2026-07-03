"""Tool module tests."""

import pytest
import json


class TestToolRegistry:
    def test_register_and_list(self):
        from tools.registry import ToolRegistry, ToolDef
        reg = ToolRegistry()
        
        def handler():
            return "ok"
        
        tool = ToolDef(name="test_tool", description="test",
                       parameters={}, handler=handler)
        reg.register(tool)
        assert reg.count() == 1
        assert reg.get("test_tool") is not None
        assert "test_tool" in reg.available_tools()

    def test_schemas_format(self):
        from tools.registry import ToolRegistry, ToolDef
        reg = ToolRegistry()
        
        def handler():
            return "ok"
        
        tool = ToolDef(name="test", description="desc",
                       parameters={"type": "object", "properties": {}},
                       handler=handler)
        reg.register(tool)
        schemas = reg.schemas()
        assert len(schemas) == 1
        assert schemas[0]["type"] == "function"
        assert schemas[0]["function"]["name"] == "test"


class TestToolExecutor:
    def test_execute_sync_tool(self):
        from tools.registry import registry, ToolDef
        from tools.executor import executor
        
        def add(a: int = 0, b: int = 0) -> str:
            return json.dumps({"result": a + b})
        
        tool = ToolDef(name="test_add", description="add two numbers",
                       parameters={}, handler=add)
        registry.register(tool)
        
        result = executor.execute("test_add", {"a": 2, "b": 3})
        data = json.loads(result)
        assert data["result"] == 5
        registry.unregister("test_add")


class TestSecurity:
    def test_destructive_commands(self):
        from tools.security import is_destructive
        assert is_destructive("rm -rf /")
        assert is_destructive("mkfs.ext4 /dev/sda")
        assert not is_destructive("ls -la")
        assert not is_destructive("python script.py")

    def test_secret_redaction(self):
        from tools.security import redact_secrets
        text = "key=sk-or-v1-abcdef123456"
        result = redact_secrets(text)
        assert "****" in result
        assert "abcdef123456" not in result
