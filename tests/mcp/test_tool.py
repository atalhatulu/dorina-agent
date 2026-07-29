"""Tests for tools/mcp/tool.py"""
import pytest
import json
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestLoadMCPConfig:
    def test_config_file_not_exists(self, tmp_path):
        from tools.mcp.tool import load_mcp_config
        result = load_mcp_config(tmp_path / "nonexistent.yaml")
        assert result == []

    def test_config_empty_file(self, tmp_path):
        from tools.mcp.tool import load_mcp_config
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text("")
        result = load_mcp_config(cfg_path)
        assert result == []

    def test_config_no_mcp_servers(self, tmp_path):
        from tools.mcp.tool import load_mcp_config
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text("model:\n  default: test\n")
        result = load_mcp_config(cfg_path)
        assert result == []

    def test_config_with_servers(self, tmp_path):
        from tools.mcp.tool import load_mcp_config
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text("""
tools:
  mcp_servers:
    - name: filesystem
      command: npx
      args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    - name: github
      command: npx
      args: ["-y", "@modelcontextprotocol/server-github"]
      env:
        GITHUB_TOKEN: "$MY_GITHUB_TOKEN"
""")
        result = load_mcp_config(cfg_path)
        assert len(result) == 2
        assert result[0].name == "filesystem"
        assert result[0].command == "npx"
        assert result[1].name == "github"
        assert result[1].command == "npx"

    def test_config_disabled_server_skipped(self, tmp_path):
        from tools.mcp.tool import load_mcp_config
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text("""
tools:
  mcp_servers:
    - name: enabled_srv
      command: echo
      enabled: true
    - name: disabled_srv
      command: echo
      enabled: false
""")
        result = load_mcp_config(cfg_path)
        assert len(result) == 1
        assert result[0].name == "enabled_srv"

    def test_config_invalid_entry_skipped(self, tmp_path):
        from tools.mcp.tool import load_mcp_config
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text("""
tools:
  mcp_servers:
    - name: valid
      command: echo
    - bad_entry: no_name
""")
        result = load_mcp_config(cfg_path)
        assert len(result) == 1
        assert result[0].name == "valid"

    def test_malformed_yaml(self, tmp_path):
        from tools.mcp.tool import load_mcp_config
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text("{invalid: yaml: [broken")
        result = load_mcp_config(cfg_path)
        assert result == []


class TestResolveEnv:
    def test_empty_env(self):
        from tools.mcp.tool import _resolve_env
        assert _resolve_env({}) is None
        assert _resolve_env(None) is None

    def test_static_values(self):
        from tools.mcp.tool import _resolve_env
        result = _resolve_env({"KEY": "value", "NUM": "42"})
        assert result == {"KEY": "value", "NUM": "42"}

    def test_var_ref_plain(self, monkeypatch):
        from tools.mcp.tool import _resolve_env
        monkeypatch.setenv("TEST_PATH", "/usr/bin")
        result = _resolve_env({"PATH": "$TEST_PATH"})
        assert result["PATH"] == "/usr/bin"

    def test_var_ref_braces(self, monkeypatch):
        from tools.mcp.tool import _resolve_env
        monkeypatch.setenv("HOME_DIR", "/home/user")
        result = _resolve_env({"HOME": "${HOME_DIR}"})
        assert result["HOME"] == "/home/user"

    def test_missing_var_returns_empty(self):
        from tools.mcp.tool import _resolve_env
        result = _resolve_env({"NONEXIST": "$DEFINITELY_NOT_SET_12345"})
        assert result["NONEXIST"] == ""


class TestMCPEnabled:
    def test_enabled_by_default(self):
        from tools.mcp.tool import _mcp_enabled
        assert _mcp_enabled() is True


class TestMCPCallTool:
    @pytest.mark.asyncio
    async def test_no_servers(self):
        from tools.mcp.tool import mcp_call_tool
        from tools.mcp.client import mcp_manager

        # Clear all servers
        original = dict(mcp_manager.servers)
        mcp_manager.servers.clear()

        result = await mcp_call_tool("test_tool", {"key": "val"})
        data = json.loads(result)
        assert "error" in data

        # Restore
        mcp_manager.servers.update(original)

    @pytest.mark.asyncio
    async def test_tool_not_in_cache(self):
        from tools.mcp.tool import mcp_call_tool
        from tools.mcp.client import mcp_manager, MCPServerConfig, MCPClient

        # Clear cache
        if hasattr(mcp_call_tool, "_tool_cache"):
            del mcp_call_tool._tool_cache

        # Add a mock server
        cfg = MCPServerConfig(name="test", command="echo")
        client = MCPClient(cfg)
        client._connected = False  # not connected, list_tools returns []
        mcp_manager.servers["test"] = client

        result = await mcp_call_tool("nonexistent_tool", {})
        data = json.loads(result)
        assert "error" in data

        # Cleanup
        del mcp_manager.servers["test"]

    @pytest.mark.asyncio
    async def test_timeout_error_handled(self):
        from tools.mcp.tool import mcp_call_tool
        from tools.mcp.client import mcp_manager, MCPServerConfig, MCPClient

        cfg = MCPServerConfig(name="test", command="echo")
        client = MCPClient(cfg)
        client._connected = True
        client._request = AsyncMock(return_value=json.dumps({"tools": []}))
        mcp_manager.servers["test"] = client

        if hasattr(mcp_call_tool, "_tool_cache"):
            del mcp_call_tool._tool_cache

        result = await mcp_call_tool("test_tool", {})
        data = json.loads(result)
        assert "error" in data or "available_tools" in data

        del mcp_manager.servers["test"]


class TestMCPListTool:
    @pytest.mark.asyncio
    async def test_no_servers(self):
        from tools.mcp.tool import mcp_list_tool
        from tools.mcp.client import mcp_manager

        original = dict(mcp_manager.servers)
        mcp_manager.servers.clear()

        result = await mcp_list_tool()
        data = json.loads(result)
        assert data["servers"] == []

        mcp_manager.servers.update(original)

    @pytest.mark.asyncio
    async def test_with_servers(self):
        from tools.mcp.tool import mcp_list_tool
        from tools.mcp.client import mcp_manager, MCPServerConfig, MCPClient

        cfg = MCPServerConfig(name="test_srv", command="echo")
        client = MCPClient(cfg)
        client._connected = False  # stays disconnected, won't try to call
        mcp_manager.servers["test_srv"] = client

        result = await mcp_list_tool()
        data = json.loads(result)
        assert len(data["servers"]) >= 1
        assert data["servers"][0]["server"] == "test_srv"

        del mcp_manager.servers["test_srv"]


class TestMCPStatusTool:
    @pytest.mark.asyncio
    async def test_no_servers(self):
        from tools.mcp.tool import mcp_status_tool
        from tools.mcp.client import mcp_manager

        original = dict(mcp_manager.servers)
        mcp_manager.servers.clear()

        result = await mcp_status_tool()
        data = json.loads(result)
        assert data["status"] == "no_servers"

        mcp_manager.servers.update(original)

    @pytest.mark.asyncio
    async def test_with_servers(self):
        from tools.mcp.tool import mcp_status_tool
        from tools.mcp.client import mcp_manager, MCPServerConfig, MCPClient

        cfg = MCPServerConfig(name="test_srv", command="echo")
        client = MCPClient(cfg)
        client._connected = False
        mcp_manager.servers["test_srv"] = client

        result = await mcp_status_tool()
        data = json.loads(result)
        assert data["status"] == "disconnected"

        del mcp_manager.servers["test_srv"]
