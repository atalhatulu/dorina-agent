"""Tests for ADR-001 (Unified RunRequest / RunResult contract) and budget hard limits."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from orchestrator.contract import RunLimits, RunRequest, RunResult, RunStatus
from core.mode_manager import modes


@pytest.fixture(autouse=True)
def clean_modes():
    modes.budget = 0
    modes.budget_hard_limit = True
    modes.reset_budget_usage()
    yield
    modes.budget = 0
    modes.budget_hard_limit = True
    modes.reset_budget_usage()


# ══════════════════════════════════════════════════════════════════════════
# ADR-001: RunRequest / RunResult Contract Verification
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_run_contract_greeting_fast_path():
    """Greeting input returns completed RunResult with 0 iterations and no LLM call."""
    from orchestrator.experimental_loop import AgentLoopV2

    loop = AgentLoopV2()
    req = RunRequest(input="merhaba", run_id="run_greet_1", session_id="sess_1")

    res = await loop.run(req)

    assert isinstance(res, RunResult)
    assert res.status == RunStatus.COMPLETED
    assert res.run_id == "run_greet_1"
    assert res.session_id == "sess_1"
    assert res.iterations == 0
    assert "Merhaba" in res.output or len(res.output) > 0


@pytest.mark.asyncio
async def test_run_contract_success_flow():
    """Normal execution returns RunResult with status COMPLETED and iterations count."""
    from orchestrator.experimental_loop import AgentLoopV2

    loop = AgentLoopV2()
    fake_response = {
        "content": "42 cevabi",
        "tool_calls": [],
        "finish_reason": "stop",
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }

    with patch.object(loop, "_think", new=AsyncMock(return_value=fake_response)):
        req = RunRequest(input="evrenin sirri nedir?", run_id="run_fact_1", session_id="sess_fact")
        res = await loop.run(req)

        assert isinstance(res, RunResult)
        assert res.status == RunStatus.COMPLETED
        assert res.output == "42 cevabi"
        assert res.run_id == "run_fact_1"
        assert res.session_id == "sess_fact"
        assert res.iterations == 1
        assert res.error is None


@pytest.mark.asyncio
async def test_run_contract_failure_flow():
    """LLM consecutive errors return RunResult with status FAILED and error populated."""
    from orchestrator.experimental_loop import AgentLoopV2

    loop = AgentLoopV2()
    fake_err = {"finish_reason": "error"}

    with patch.object(loop, "_think", new=AsyncMock(return_value=fake_err)):
        req = RunRequest(input="hatali sorgu", run_id="run_fail_1")
        res = await loop.run(req)

        assert isinstance(res, RunResult)
        assert res.status == RunStatus.FAILED
        assert res.error is not None
        assert "LLM failed after 3 consecutive errors" in res.error
        assert res.output == res.error


@pytest.mark.asyncio
async def test_process_backward_compatibility():
    """process() still returns a plain string, wrapping run() transparently."""
    from orchestrator.experimental_loop import AgentLoopV2

    loop = AgentLoopV2()
    fake_response = {
        "content": "Geriye donuk uyumlu sonuc",
        "tool_calls": [],
        "finish_reason": "stop",
    }

    with patch.object(loop, "_think", new=AsyncMock(return_value=fake_response)):
        output = await loop.process("test sorgusu")
        assert isinstance(output, str)
        assert output == "Geriye donuk uyumlu sonuc"


# ══════════════════════════════════════════════════════════════════════════
# Budget Hard Limit Verification
# ══════════════════════════════════════════════════════════════════════════

def test_mode_manager_budget_properties():
    """ModeManager must correctly report budget exhaustion and support hard limit toggling."""
    modes.budget = 1000
    modes.budget_hard_limit = True
    assert modes.budget == 1000
    assert modes.budget_remaining == 1000
    assert modes.is_budget_exhausted() is False

    # Simulate token usage under limit
    modes.budget_hit(500)
    assert modes.budget_used == 500
    assert modes.budget_remaining == 500
    assert modes.is_budget_exhausted() is False

    # Exceed limit
    modes.budget_hit(600)
    assert modes.budget_used == 1100
    assert modes.budget_remaining == 0
    assert modes.is_budget_exhausted() is True

    # Reset
    modes.reset_budget_usage()
    assert modes.budget_used == 0
    assert modes.is_budget_exhausted() is False


@pytest.mark.asyncio
async def test_budget_hard_limit_halts_before_llm_call():
    """When budget is exhausted and hard limit is active, execution halts immediately."""
    from orchestrator.experimental_loop import AgentLoopV2

    loop = AgentLoopV2()
    modes.budget = 500
    modes.budget_hard_limit = True
    modes.budget_hit(600)  # already breached

    think_mock = AsyncMock()
    with patch.object(loop, "_think", new=think_mock):
        req = RunRequest(input="pahali bir sorgu", run_id="run_budget_1")
        res = await loop.run(req)

        assert res.status == RunStatus.BUDGET_EXCEEDED
        assert "Token budget exceeded" in res.output
        assert res.error == "Token budget exceeded"
        # Must not have called LLM!
        assert think_mock.call_count == 0


@pytest.mark.asyncio
async def test_budget_breached_during_response_halts_execution():
    """If LLM response breaches budget and hard limit is active, loop terminates with BUDGET_EXCEEDED."""
    from orchestrator.experimental_loop import AgentLoopV2

    loop = AgentLoopV2()
    modes.budget = 1000
    modes.budget_hard_limit = True

    fake_response = {
        "content": "Pahali yanit",
        "tool_calls": [{"id": "t1", "function": {"name": "dummy_tool", "arguments": "{}"}}],
        "finish_reason": "stop",
        "_budget_breached": True,
    }

    with patch.object(loop, "_think", new=AsyncMock(return_value=fake_response)):
        req = RunRequest(input="bütçeyi aşan sorgu")
        res = await loop.run(req)

        assert res.status == RunStatus.BUDGET_EXCEEDED
        assert "Token budget exceeded" in res.output
        # Sıkıştırma çağrısı yapılmamalı (LLM compression storm yok)
        assert loop.compressor.compression_count == 0


@pytest.mark.asyncio
async def test_a2a_endpoint_uses_contract_and_reports_accurate_status(monkeypatch):
    """A2A endpoint accurately marks tasks as failed when LLM or budget fails."""
    import gateway.a2a
    from gateway.app import app
    from fastapi.testclient import TestClient
    from orchestrator.experimental_loop import loop_v2

    monkeypatch.setattr(gateway.a2a, "is_auth_enabled", lambda: False)
    client = TestClient(app)

    fake_err = {"finish_reason": "error"}
    with patch.object(loop_v2, "_think", new=AsyncMock(return_value=fake_err)):
        resp = client.post(
            "/a2a",
            json={
                "jsonrpc": "2.0",
                "id": "a2a_1",
                "method": "tasks/send",
                "params": {"message": {"parts": [{"text": "hata verecek komut"}]}},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["result"]["status"] == "failed"
        assert "error" in data["result"]
        assert "LLM failed" in data["result"]["error"]
