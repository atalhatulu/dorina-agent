"""Tests for tools/mcp/client.py"""
import pytest
import json
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestMCPToolDef:
    def test_creation(self):
        from tools.mcp.client import MCPToolDef
        t = MCPToolDef(name="test_tool", description="A test", input_schema={}, server_name="test_srv")
        assert t.name == "test_tool"
        assert t.description == "A test"
        assert t.input_schema == {}
        assert t.server_name == "test_srv"


class TestMCPServerConfig:
    def test_defaults(self):
        from tools.mcp.client import MCPServerConfig
        c = MCPServerConfig(name="test", command="echo")
        assert c.name == "test"
        assert c.command == "echo"
        assert c.args == []
        assert c.env is None
        assert c.enabled is True

    def test_with_args(self):
        from tools.mcp.client import MCPServerConfig
        c = MCPServerConfig(name="gh", command="npx", args=["-y", "@modelcontextprotocol/server-github"])
        assert c.args == ["-y", "@modelcontextprotocol/server-github"]


class TestMCPClient:
    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self):
        """disconnect should be safe when not connected."""
        from tools.mcp.client import MCPClient, MCPServerConfig
        cfg = MCPServerConfig(name="test", command="echo")
        client = MCPClient(cfg)
        await client.disconnect()
        assert client._connected is False

    @pytest.mark.asyncio
    async def test_list_tools_when_not_connected(self):
        """list_tools should return empty list when not connected."""
        from tools.mcp.client import MCPClient, MCPServerConfig
        cfg = MCPServerConfig(name="test", command="echo")
        client = MCPClient(cfg)
        tools = await client.list_tools()
        assert tools == []

    @pytest.mark.asyncio
    async def test_call_tool_when_not_connected(self):
        """call_tool should return error json when not connected."""
        from tools.mcp.client import MCPClient, MCPServerConfig
        cfg = MCPServerConfig(name="test", command="echo")
        client = MCPClient(cfg)
        result = await client.call_tool("test", {})
        data = json.loads(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_handle_message_response(self):
        """_handle_message should resolve pending future for matching id."""
        from tools.mcp.client import MCPClient, MCPServerConfig
        cfg = MCPServerConfig(name="test", command="echo")
        client = MCPClient(cfg)
        fut = asyncio.get_event_loop().create_future()
        client._pending["1"] = fut

        client._handle_message({"id": 1, "result": {"ok": True}})
        assert fut.done()
        result = json.loads(fut.result())
        assert result["result"]["ok"] is True

    @pytest.mark.asyncio
    async def test_handle_message_error(self):
        """_handle_message should log error but no crash."""
        from tools.mcp.client import MCPClient, MCPServerConfig
        cfg = MCPServerConfig(name="test", command="echo")
        client = MCPClient(cfg)
        client._handle_message({"error": {"code": -32601, "message": "Method not found"}})

    @pytest.mark.asyncio
    async def test_handle_message_notification(self):
        """_handle_message should handle notifications without crash."""
        from tools.mcp.client import MCPClient, MCPServerConfig
        cfg = MCPServerConfig(name="test", command="echo")
        client = MCPClient(cfg)
        client._handle_message({"method": "notifications/initialized"})

    @pytest.mark.asyncio
    async def test_connect_with_env_var_resolution(self):
        """connect should resolve $VAR references in env."""
        from tools.mcp.client import MCPClient, MCPServerConfig
        import os
        os.environ["_MCP_TEST_VAR"] = "resolved_value"

        cfg = MCPServerConfig(
            name="test",
            command="python3",
            args=["-c", "print('ok')"],
            env={"MY_VAR": "$_MCP_TEST_VAR", "STATIC": "hello"},
        )
        client = MCPClient(cfg)

        # Mock subprocess creation
        mock_process = MagicMock()
        mock_process.stdout = AsyncMock()
        mock_process.stdout.readline = AsyncMock(return_value=b"")
        mock_process.stdin = MagicMock()
        mock_process.stderr = AsyncMock()
        mock_process.stderr.readline = AsyncMock(return_value=b"")

        mock_create = AsyncMock(return_value=mock_process)

        with patch.object(asyncio, "create_subprocess_exec", mock_create):
            with patch.object(client, "_request", AsyncMock(return_value=json.dumps({"ok": True}))):
                with patch.object(client, "_notify", AsyncMock()):
                    await client.connect()

        assert mock_create.called
        call_kwargs = mock_create.call_args[1]
        env = call_kwargs["env"]
        assert env["MY_VAR"] == "resolved_value"
        assert env["STATIC"] == "hello"

    @pytest.mark.asyncio
    async def test_connect_failure_cleanup(self):
        """connect failure should call disconnect."""
        from tools.mcp.client import MCPClient, MCPServerConfig
        cfg = MCPServerConfig(name="test", command="nonexistent-command-12345")
        client = MCPClient(cfg)

        with patch.object(client, "disconnect", AsyncMock()) as mock_disconnect:
            with patch.object(asyncio, "create_subprocess_exec", AsyncMock(side_effect=OSError("not found"))):
                with pytest.raises(OSError):
                    await client.connect()
                mock_disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_ping_when_not_connected(self):
        """ping should return False when not connected."""
        from tools.mcp.client import MCPClient, MCPServerConfig
        cfg = MCPServerConfig(name="test", command="echo")
        client = MCPClient(cfg)
        result = await client.ping()
        assert result is False

    @pytest.mark.asyncio
    async def test_ping_when_not_connected_returns_false(self):
        """ping should return False when writer is None."""
        from tools.mcp.client import MCPClient, MCPServerConfig
        cfg = MCPServerConfig(name="test", command="echo")
        client = MCPClient(cfg)
        result = await client.ping()
        assert result is False

    @pytest.mark.asyncio
    async def test_request_method(self):
        """_request should send JSON-RPC and wait for response."""
        from tools.mcp.client import MCPClient, MCPServerConfig
        cfg = MCPServerConfig(name="test", command="echo")
        client = MCPClient(cfg)

        # Setup mock writer with async drain
        mock_writer = MagicMock()
        mock_writer.write = MagicMock()
        mock_writer.drain = AsyncMock()
        client.writer = mock_writer

        # Setup future that's already resolved
        fut = asyncio.get_event_loop().create_future()
        fut.set_result(json.dumps({"jsonrpc": "2.0", "id": "1", "result": {"ok": True}}))

        # Code uses get_running_loop() — patch that, not the deprecated get_event_loop
        with patch.object(asyncio, "get_running_loop") as mock_loop:
            mock_loop_instance = MagicMock()
            mock_loop_instance.create_future.return_value = fut
            mock_loop.return_value = mock_loop_instance
            result = await client._request("test_method", {"param": 1})

        data = json.loads(result)
        assert "result" in data
        assert data["result"]["ok"] is True

    @pytest.mark.asyncio
    async def test_notify(self):
        """_notify should send JSON-RPC notification."""
        from tools.mcp.client import MCPClient, MCPServerConfig
        cfg = MCPServerConfig(name="test", command="echo")
        client = MCPClient(cfg)
        client.writer = MagicMock()
        client.writer.drain = AsyncMock()

        await client._notify("notifications/initialized")
        assert client.writer.write.called

    @pytest.mark.asyncio
    async def test_disconnect_with_process(self):
        """disconnect should terminate process."""
        from tools.mcp.client import MCPClient, MCPServerConfig
        cfg = MCPServerConfig(name="test", command="echo")
        client = MCPClient(cfg)
        client._connected = True

        mock_process = MagicMock()
        mock_process.terminate = MagicMock()
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.returncode = None  # still running
        client.process = mock_process

        mock_writer = MagicMock()
        mock_writer.close = MagicMock()
        mock_writer.wait_closed = AsyncMock()
        client.writer = mock_writer

        await client.disconnect()
        assert client._connected is False
        assert client.writer is None
        assert client.process is None


class TestMCPManager:
    @pytest.mark.asyncio
    async def test_add_server(self):
        from tools.mcp.client import MCPManager, MCPServerConfig
        mgr = MCPManager()
        cfg = MCPServerConfig(name="test", command="echo")
        mgr.add_server(cfg)
        assert "test" in mgr.servers
        assert len(mgr.configs) == 1

    @pytest.mark.asyncio
    async def test_remove_server(self):
        from tools.mcp.client import MCPManager, MCPServerConfig
        mgr = MCPManager()
        cfg = MCPServerConfig(name="test", command="echo")
        mgr.add_server(cfg)
        mgr.remove_server("test")
        assert "test" not in mgr.servers

    @pytest.mark.asyncio
    async def test_list_all_tools_empty(self):
        from tools.mcp.client import MCPManager
        mgr = MCPManager()
        tools = await mgr.list_all_tools()
        assert tools == []

    @pytest.mark.asyncio
    async def test_ping_all_empty(self):
        from tools.mcp.client import MCPManager
        mgr = MCPManager()
        results = await mgr.ping_all()
        assert results == {}

    @pytest.mark.asyncio
    async def test_call_tool_not_found(self):
        from tools.mcp.client import MCPManager
        mgr = MCPManager()
        result = await mgr.call_tool("nonexistent", {})
        data = json.loads(result)
        assert "error" in data
