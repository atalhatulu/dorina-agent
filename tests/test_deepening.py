"""Tests for deepened capabilities:
- Resilient tokenizer under cold-cache network errors and non-empty bounds
- WebSocket chat delivery of typed ADR-001 run status and run_id
- CLI single query exit code determination (0 vs 1)
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


# ══════════════════════════════════════════════════════════════════════════
# Tokenizer Offline / Network Error Resilience
# ══════════════════════════════════════════════════════════════════════════

def test_tokenizer_handles_network_failure_and_bounds():
    """Tokenizer must never crash on network failure during cold encoding fetch."""
    import core.tokenizer as tok

    # Reset cache to simulate cold cache
    tok._encoding_cache.clear()

    # Simulate network failure during get_encoding
    with patch("tiktoken.get_encoding", side_effect=OSError("Network is unreachable (offline sandbox)")):
        # Non-empty string must return >= 1 token
        count = tok.count_tokens("hello world this is a resilient test")
        assert count > 0

        # Short 1-2 char words must not return 0 tokens
        assert tok.count_tokens("a") >= 1
        assert tok.count_tokens("hi") >= 1

        # Empty string must still return 0
        assert tok.count_tokens("") == 0

    # Messages token counting must also survive
    with patch("tiktoken.get_encoding", side_effect=OSError("No route to host")):
        msgs = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "world"},
        ]
        msg_tokens = tok.count_messages_tokens(msgs)
        assert msg_tokens >= 2


# ══════════════════════════════════════════════════════════════════════════
# WebSocket Typed Status & Run Contract
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_websocket_chat_delivers_run_status_and_id():
    """WebSocket /ws/chat returns typed status, run_id, and completed envelope."""
    from gateway.app import app
    from fastapi.testclient import TestClient
    from orchestrator.experimental_loop import loop_v2
    from orchestrator.contract import RunResult, RunStatus

    client = TestClient(app)

    fake_result = RunResult(
        status=RunStatus.COMPLETED,
        output="Mock websocket response",
        run_id="run_ws_123",
        session_id="ws_sess",
        iterations=1,
    )

    with patch.object(loop_v2, "run", new=AsyncMock(return_value=fake_result)):
        with client.websocket_connect("/ws/chat") as ws:
            # First message on connect is session info
            sess_msg = ws.receive_json()
            assert sess_msg["type"] == "session"

            ws.send_json({"query": "selam websocket", "session_id": "ws_sess"})

            # Second message: echo user
            msg1 = ws.receive_json()
            assert msg1["type"] == "user"

            # Third message: assistant response with ADR-001 status
            msg2 = ws.receive_json()
            assert msg2["type"] == "assistant"
            assert msg2["content"] == "Mock websocket response"
            assert msg2["status"] == "completed"
            assert msg2["run_id"] == "run_ws_123"
            assert msg2["done"] is True


@pytest.mark.asyncio
async def test_websocket_chat_reports_failed_status_on_error():
    """WebSocket chat accurately marks failed status when run fails."""
    from gateway.app import app
    from fastapi.testclient import TestClient
    from orchestrator.experimental_loop import loop_v2
    from orchestrator.contract import RunResult, RunStatus

    client = TestClient(app)

    fake_fail = RunResult(
        status=RunStatus.FAILED,
        output="LLM 3 kez hata verdi.",
        error="LLM 3 kez hata verdi.",
        run_id="run_ws_err",
        session_id="ws_sess",
        iterations=3,
    )

    with patch.object(loop_v2, "run", new=AsyncMock(return_value=fake_fail)):
        with client.websocket_connect("/ws/chat") as ws:
            # Session info
            ws.receive_json()

            ws.send_json({"query": "hata ver", "session_id": "ws_sess"})
            ws.receive_json()  # user echo

            msg2 = ws.receive_json()
            assert msg2["type"] == "assistant"
            assert msg2["status"] == "failed"
            assert msg2["error"] == "LLM 3 kez hata verdi."
            assert msg2["done"] is True


# ══════════════════════════════════════════════════════════════════════════
# CLI Single Query Exit Codes
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cli_run_single_query_returns_correct_exit_codes():
    """DorinaApp.run_single_query must return 0 on success, 1 on failure or budget breach."""
    from app import DorinaApp
    from orchestrator.contract import RunResult, RunStatus
    from orchestrator.experimental_loop import loop_v2

    app_instance = DorinaApp()
    app_instance.session_id = "test_cli_sess"

    # 1. Empty query -> 0
    assert await app_instance.run_single_query("") == 0

    # 2. Successful query -> 0
    ok_res = RunResult(status=RunStatus.COMPLETED, output="Başarılı sonuç")
    with patch.object(loop_v2, "run", new=AsyncMock(return_value=ok_res)):
        code = await app_instance.run_single_query("basarili sorgu")
        assert code == 0

    # 3. Failed query -> 1
    fail_res = RunResult(status=RunStatus.FAILED, output="Hata oluştu", error="Hata oluştu")
    with patch.object(loop_v2, "run", new=AsyncMock(return_value=fail_res)):
        code = await app_instance.run_single_query("hatali sorgu")
        assert code == 1

    # 4. Budget exceeded -> 1
    budget_res = RunResult(status=RunStatus.BUDGET_EXCEEDED, output="Bütçe aşıldı", error="Bütçe aşıldı")
    with patch.object(loop_v2, "run", new=AsyncMock(return_value=budget_res)):
        code = await app_instance.run_single_query("pahali sorgu")
        assert code == 1
