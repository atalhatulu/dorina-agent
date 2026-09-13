"""Bounded loop retries and independent session persistence regressions."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def isolated_loop():
    from orchestrator import experimental_loop as module

    loop = module.AgentLoopV2()
    loop._session_titled = True
    loop._skills_injected = True
    loop._system_prompt = "test"
    loop.compressor.should_compress = MagicMock(return_value=False)
    loop._schedule_save = MagicMock()
    with patch.object(module, "_display", MagicMock()), patch.object(module, "_status", MagicMock()), patch.object(module, "get_active_schemas", return_value=[]), patch.object(module, "is_greeting", return_value=False), patch.object(module.modes, "is_on", return_value=False):
        yield loop


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["too_many_tools", "terminal_info", "terminal_consolidation", "empty"])
async def test_rejected_or_empty_responses_consume_budget(isolated_loop, kind):
    from orchestrator import experimental_loop as module

    tool_calls = []
    if kind != "empty":
        commands = ["pwd", "ls", "uname"] if kind == "terminal_info" else ["echo a", "echo b", "echo c"]
        tool_calls = [{"id": f"call_{i}", "function": {"name": "web_search" if kind == "too_many_tools" else "terminal", "arguments": json.dumps({"command": commands[i % 3], "query": str(i)})}} for i in range(5 if kind == "too_many_tools" else 3)]
    repeated = {"content": "", "tool_calls": tool_calls, "usage": {}}
    isolated_loop.reasoning.think = AsyncMock(side_effect=[repeated] * 6 + [{"content": "unexpected success", "tool_calls": []}])
    with patch.object(module, "_MAX_LOOP_ITERATIONS", 2), patch.object(module.executor, "async_execute_json", new_callable=AsyncMock, return_value="ok"):
        result = await isolated_loop.process("bounded test")
    assert result == "Maximum iterations reached."
    assert isolated_loop.reasoning.think.await_count == 2
    assert isolated_loop._loop_iterations == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("budget,expected_calls", [(0, 0), (1, 1), (2, 2), (10, 3)])
async def test_provider_errors_stop_without_recursive_budget_bypass(isolated_loop, budget, expected_calls):
    from orchestrator import experimental_loop as module

    isolated_loop.reasoning.think = AsyncMock(side_effect=RuntimeError("provider down"))
    with patch.object(module, "_MAX_LOOP_ITERATIONS", budget), patch.object(module.asyncio, "sleep", new_callable=AsyncMock):
        result = await isolated_loop.process("failure test")
    assert isolated_loop.reasoning.think.await_count == expected_calls
    if budget < 3:
        assert "Maximum iterations" in result
    else:
        assert "LLM failed" in result


@pytest.mark.asyncio
async def test_new_turn_gets_fresh_error_budget(isolated_loop):
    from orchestrator import experimental_loop as module

    isolated_loop._consecutive_llm_errors = 3
    isolated_loop.reasoning.think = AsyncMock(side_effect=[RuntimeError("temporary"), {"content": "recovered", "tool_calls": [], "usage": {}}])
    with patch.object(module.asyncio, "sleep", new_callable=AsyncMock):
        result = await isolated_loop.process("retry test")
    assert result == "recovered"
    assert isolated_loop.reasoning.think.await_count == 2


@pytest.mark.asyncio
async def test_rejected_calls_have_explicit_tool_results(isolated_loop):
    calls = [{"id": f"call_{i}", "function": {"name": "web_search", "arguments": "{}"}} for i in range(5)]
    isolated_loop._add_tool_call_message(calls)
    await isolated_loop._execute_tools(calls)
    results = [m for m in isolated_loop.context.get_messages() if m["role"] == "tool"]
    assert {m["tool_call_id"] for m in results} == {c["id"] for c in calls}
    assert all("error" in m["content"] for m in results)


@pytest.fixture
def isolated_manager(monkeypatch):
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    import importlib

    module = importlib.import_module("session.manager")
    engine = create_engine("sqlite:///:memory:")
    module.Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("CREATE VIRTUAL TABLE session_fts USING fts5(session_id UNINDEXED, content)"))
    monkeypatch.setattr(module, "SessionLocal", sessionmaker(bind=engine))
    monkeypatch.setattr(module, "_encrypt", lambda value: value)
    monkeypatch.setattr(module, "_decrypt", lambda value: value)
    monkeypatch.setattr(module, "count_messages_tokens", lambda messages: len(messages))
    manager = module.SessionManager()
    yield manager
    manager.db.close()
    engine.dispose()


def test_identical_messages_are_saved_in_both_sessions(isolated_manager):
    messages = [{"role": "user", "content": "same message"}]
    first = isolated_manager.create()
    isolated_manager.save(messages)
    second = isolated_manager.create()
    isolated_manager.save(messages)
    assert isolated_manager.load(first)["messages"] == messages
    assert isolated_manager.load(second)["messages"] == messages


def test_failed_save_can_retry_identical_payload(isolated_manager):
    session_id = isolated_manager.create()
    messages = [{"role": "user", "content": "must persist"}]
    with patch.object(isolated_manager.db, "commit", side_effect=RuntimeError("transient write failure")):
        with pytest.raises(RuntimeError):
            isolated_manager.save(messages)
    isolated_manager.db.rollback()
    isolated_manager.save(messages)
    isolated_manager.db.expire_all()
    assert isolated_manager.load(session_id)["messages"] == messages
