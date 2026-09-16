"""Deep verification tests for P2 audit findings:
- F14: MCP client pending leak prevention, JSON-RPC error handling, EOF connection cleanup, qualified server:tool routing
- F15: Broadcaster thread-safe dispatch from worker threads and runtime label accuracy for completed forks
- F13: Context compressor prevents compression storms within the same turn
"""

import asyncio
import json
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ══════════════════════════════════════════════════════════════════════════
# F14: MCP Client, Error Handling, Routing & Cache Invalidation
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_mcp_client_pending_cleanup_on_cancel_or_timeout():
    """Cancelled or timed out requests must be popped from _pending to prevent leaks."""
    from tools.mcp.client import MCPClient, MCPServerConfig

    config = MCPServerConfig(name="test_srv", command="dummy_cmd")
    client = MCPClient(config)
    client._connected = True
    client.writer = MagicMock()
    client.writer.drain = AsyncMock()
    client.writer.write = MagicMock()

    # Create a request with an immediate timeout
    with pytest.raises((TimeoutError, asyncio.TimeoutError)):
        await client._request("test_method", {}, timeout=0.01)

    # _pending must be cleaned up
    assert len(client._pending) == 0


@pytest.mark.asyncio
async def test_mcp_client_connection_error_on_eof():
    """EOF in _read_loop must mark client as disconnected and fail pending futures."""
    from tools.mcp.client import MCPClient, MCPServerConfig

    config = MCPServerConfig(name="test_srv", command="dummy_cmd")
    client = MCPClient(config)
    client._connected = True
    loop = asyncio.get_running_loop()

    # Attach two pending futures
    fut1 = loop.create_future()
    fut2 = loop.create_future()
    client._pending["1"] = fut1
    client._pending["2"] = fut2

    # Mock readline to simulate EOF (empty bytes)
    mock_reader = AsyncMock()
    mock_reader.readline = AsyncMock(return_value=b"")
    client.reader = mock_reader

    # Run _read_loop
    await client._read_loop()

    assert client._connected is False
    assert len(client._pending) == 0

    assert isinstance(fut1.exception(), ConnectionError)
    assert "MCP connection closed" in str(fut1.exception())
    assert isinstance(fut2.exception(), ConnectionError)
    assert "MCP connection closed" in str(fut2.exception())


@pytest.mark.asyncio
async def test_mcp_client_jsonrpc_error_handling():
    """JSON-RPC error payload should reject the pending future with MCPError and return clean dict."""
    from tools.mcp.client import MCPClient, MCPServerConfig, MCPError

    config = MCPServerConfig(name="test_srv", command="dummy_cmd")
    client = MCPClient(config)
    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    client._pending["42"] = fut

    # Message with JSON-RPC error
    client._handle_message({
        "jsonrpc": "2.0",
        "id": "42",
        "error": {"code": -32601, "message": "Method not found", "data": "extra details"}
    })

    assert fut.done()
    with pytest.raises(MCPError) as exc_info:
        fut.result()
    assert exc_info.value.code == -32601
    assert "Method not found" in exc_info.value.message

    # Test call_tool catches MCPError and formats error response
    client._connected = True
    with patch.object(client, "_request", side_effect=MCPError({"code": -32000, "message": "Tool failed"})):
        res = await client.call_tool("failing_tool", {})
        res_data = json.loads(res)
        assert res_data.get("code") == -32000
        assert "Tool failed" in res_data.get("error", "")


@pytest.mark.asyncio
async def test_mcp_server_qualified_routing():
    """MCPManager and mcp_call_tool should resolve server:tool qualified names."""
    from tools.mcp.client import MCPClient, MCPServerConfig, MCPManager
    from tools.mcp.tool import mcp_call_tool, mcp_invalidate_cache

    manager = MCPManager()
    cfg_a = MCPServerConfig(name="serverA", command="cmdA")
    cfg_b = MCPServerConfig(name="serverB", command="cmdB")
    client_a = MCPClient(cfg_a)
    client_b = MCPClient(cfg_b)
    client_a._connected = True
    client_b._connected = True

    client_a.call_tool = AsyncMock(return_value="result_from_A")
    client_b.call_tool = AsyncMock(return_value="result_from_B")

    manager.servers = {"serverA": client_a, "serverB": client_b}

    # Direct routing via manager
    res_a = await manager.call_tool("serverA:toolX", {"arg": 1})
    assert res_a == "result_from_A"
    client_a.call_tool.assert_called_with("toolX", {"arg": 1})

    res_b = await manager.call_tool("serverB:toolY", {"arg": 2})
    assert res_b == "result_from_B"
    client_b.call_tool.assert_called_with("toolY", {"arg": 2})

    # Unknown server in qualified name
    res_err = await manager.call_tool("serverC:toolZ", {})
    err_data = json.loads(res_err)
    assert "serverC" in err_data.get("error", "")

    # Invalidate cache test
    mcp_invalidate_cache()


# ══════════════════════════════════════════════════════════════════════════
# F15: Broadcaster Thread-safety & Runtime Status
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_broadcaster_threadsafe_dispatch_from_worker_thread():
    """Broadcaster must safely deliver messages published from background worker threads."""
    import gateway.runtime as runtime

    mock_ws = AsyncMock()
    received_payloads = []

    async def fake_send_json(data):
        received_payloads.append(data)

    mock_ws.send_json = fake_send_json

    loop = asyncio.get_running_loop()
    runtime.set_loop(loop)
    runtime.subscribe(mock_ws)

    # Run broadcast from a separate worker thread with no event loop
    worker_called = threading.Event()

    def worker_target():
        runtime.worker_event("auditor", "running", progress=50)
        worker_called.set()

    t = threading.Thread(target=worker_target)
    t.start()
    t.join(timeout=2.0)
    assert worker_called.is_set()

    # Allow the event loop to run queued tasks
    await asyncio.sleep(0.1)

    # Verify message received by websocket
    types = [p.get("type") for p in received_payloads]
    assert "worker" in types

    runtime.unsubscribe(mock_ws)


def test_runtime_label_idle_when_forks_completed():
    """Runtime label must be IDLE when all forks and workers are completed/done."""
    from gateway.runtime import _runtime_label

    # All forks completed
    state = {
        "workers": [{"role": "planner", "status": "completed"}],
        "forks": [
            {"id": "fork-1", "status": "completed"},
            {"id": "fork-2", "status": "failed"},
        ],
    }
    label = _runtime_label(state)
    assert label["label"] == "IDLE"
    assert label["level"] == "idle"

    # Active fork makes it RUNNING · SUBAGENT
    state_active = {
        "workers": [],
        "forks": [
            {"id": "fork-1", "status": "completed"},
            {"id": "fork-2", "status": "running"},
        ],
    }
    label_active = _runtime_label(state_active)
    assert label_active["label"] == "RUNNING · SUBAGENT"
    assert label_active["level"] == "running"


# ══════════════════════════════════════════════════════════════════════════
# F13: Context Compressor Storm Prevention
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_compressor_prevents_compression_storm_same_turn():
    """ContextCompressor must only compress once proactively per turn."""
    from orchestrator.compressor import ContextCompressor

    compressor = ContextCompressor(max_tokens=100000)
    messages = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "Turn 1"},
        {"role": "assistant", "content": "Answer 1"},
        {"role": "user", "content": "Turn 2"},
        {"role": "assistant", "content": "Answer 2"},
        {"role": "user", "content": "Turn 3"},
        {"role": "assistant", "content": "Answer 3"},
        {"role": "user", "content": "Turn 4"},
        {"role": "assistant", "content": "Answer 4"},
    ]

    # Turn 4 check 1: should compress
    assert compressor.should_compress(messages, turn_count=4) is True

    # Compress for turn 4
    compressed = await compressor.compress(messages, turn_count=4)
    assert compressor._last_compressed_turn == 4

    # Turn 4 check 2 (e.g. after tool 1 completes in turn 4): should NOT compress again!
    assert compressor.should_compress(compressed, turn_count=4) is False

    # Turn 5: not multiple of 4, should NOT compress
    assert compressor.should_compress(compressed, turn_count=5) is False

    # Turn 8: next multiple of 4, should compress!
    assert compressor.should_compress(compressed, turn_count=8) is True


def test_compressor_safety_net_triggers_on_overflow():
    """Even in the same turn, if token ratio exceeds threshold, safety net triggers."""
    from orchestrator.compressor import ContextCompressor

    # Very small max_tokens so threshold (50%) is easily exceeded
    compressor = ContextCompressor(max_tokens=50)
    compressor._last_compressed_turn = 4

    long_messages = [
        {"role": "user", "content": "A very long message " * 100}
    ]

    # Even though _last_compressed_turn == 4, token ratio exceeds 0.50
    assert compressor.should_compress(long_messages, turn_count=4) is True


def test_compressor_reset():
    """Reset must clear last compressed turn and history."""
    from orchestrator.compressor import ContextCompressor

    compressor = ContextCompressor()
    compressor.compression_count = 5
    compressor._last_compressed_turn = 8
    compressor._previous_summaries = ["summary 1"]

    compressor.reset()

    assert compressor.compression_count == 0
    assert compressor._last_compressed_turn == -1
    assert len(compressor._previous_summaries) == 0
