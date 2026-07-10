"""Tests for AgentLoopV2 (experimental_loop.py)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def fresh_loop():
    """Fresh AgentLoopV2 per test."""
    from orchestrator.experimental_loop import AgentLoopV2, _FILE_CACHE
    _FILE_CACHE.clear()
    loop = AgentLoopV2()
    yield loop


@pytest.fixture(autouse=True)
def _mock_ui():
    """Prevent UI imports from failing in test env."""
    with patch.multiple(
        "orchestrator.experimental_loop",
        _status=MagicMock(),
        _display=MagicMock(),
    ):
        yield


@pytest.fixture(autouse=True)
def _mock_session_manager():
    """Prevent session manager side effects."""
    with patch("orchestrator.experimental_loop.session_manager") as mock:
        mock.current_id = "test-session"
        mock.save = MagicMock()
        yield mock


@pytest.fixture(autouse=True)
def _mock_soul():
    """Stub soul.system_prompt."""
    with patch("orchestrator.experimental_loop.soul") as mock:
        mock.system_prompt = "You are a helpful assistant."
        mock.system_prompt_short = "Be brief."
        yield mock


# ── Test: Basic response (no tool calls) ─────────────────────────────────


class TestBasicResponse:
    """Basit soru — tool cagirmamali, direkt yanit vermeli."""

    @pytest.mark.asyncio
    async def test_simple_question_returns_content(self, fresh_loop):
        """Kullanici basit bir soru sordugunda loop direkt yanit donmeli."""
        loop = fresh_loop
        mock_think = AsyncMock(return_value={
            "content": "Istanbul 1453'te fethedildi.",
            "tool_calls": [],
            "usage": {"prompt_tokens": 50, "completion_tokens": 10},
        })
        loop.reasoning.think = mock_think

        result = await loop.process("Istanbul ne zaman fethedildi?")

        assert "1453" in result
        mock_think.assert_called_once()

    @pytest.mark.asyncio
    async def test_greeting_no_llm_call(self, fresh_loop):
        """Selam mesaji LLM cagrisi yapmamali."""
        loop = fresh_loop
        loop.reasoning.think = AsyncMock()

        result = await loop.process("merhaba")

        assert "How can I help" in result or "Hello" in result
        loop.reasoning.think.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_tool_calls_and_content_retry(self, fresh_loop):
        """Bos yanit gelince retry yapmali."""
        loop = fresh_loop
        loop.reasoning.think = AsyncMock(side_effect=[
            {"content": "", "tool_calls": [], "usage": {}},
            {"content": "Istanbul 1453.", "tool_calls": [], "usage": {}},
        ])

        result = await loop.process("Istanbul ne zaman?")

        assert result == "Istanbul 1453."
        assert loop.reasoning.think.call_count == 2

    @pytest.mark.asyncio
    async def test_sanitize_removes_control_chars(self, fresh_loop):
        """Kontrol karakterleri sanitize edilmeli."""
        loop = fresh_loop
        mock_think = AsyncMock(return_value={
            "content": "response",
            "tool_calls": [],
            "usage": {},
        })
        loop.reasoning.think = mock_think

        result = await loop.process("hello\x00world\x1f")

        assert result == "response"
        # Check that sanitized text was added to context
        msg = loop.context.get_messages()[0]["content"]
        assert "\x00" not in msg
        assert "\x1f" not in msg


# ── Test: Tool execution ──────────────────────────────────────────────────


class TestToolExecution:
    """Tool cagirma senaryolari."""

    @pytest.mark.asyncio
    async def test_read_file_calls_executor(self, fresh_loop):
        """read_file tool'u executor uzerinden calismali."""
        loop = fresh_loop

        # Mock think: once return a tool call, then return response
        think_responses = [
            {
                "content": "",
                "tool_calls": [{
                    "id": "call_1",
                    "function": {"name": "read_file", "arguments": '{"path": "/tmp/test.txt"}'},
                }],
                "usage": {"prompt_tokens": 60, "completion_tokens": 5},
            },
            {
                "content": "Here is the file content: hello world",
                "tool_calls": [],
                "usage": {"prompt_tokens": 100, "completion_tokens": 10},
            },
        ]
        loop.reasoning.think = AsyncMock(side_effect=think_responses)

        with patch("orchestrator.experimental_loop.executor.async_execute_json",
                   AsyncMock(return_value="hello world")):
            result = await loop.process("dosyayi oku")

        assert "hello world" in result

    @pytest.mark.asyncio
    async def test_parallel_read_tools(self, fresh_loop):
        """Birden fazla read tool'u paralel calismali."""
        loop = fresh_loop

        think_responses = [
            {
                "content": "",
                "tool_calls": [
                    {"id": "c1", "function": {"name": "read_file", "arguments": '{"path": "/a.txt"}'}},
                    {"id": "c2", "function": {"name": "search_files", "arguments": '{"pattern": "test"}'}},
                ],
                "usage": {},
            },
            {
                "content": "done",
                "tool_calls": [],
                "usage": {},
            },
        ]
        loop.reasoning.think = AsyncMock(side_effect=think_responses)

        with patch("orchestrator.experimental_loop.executor.async_execute_json",
                   AsyncMock(return_value="result")):
            result = await loop.process("oku ve ara")

        assert result == "done"

    @pytest.mark.asyncio
    async def test_sequential_write_tools(self, fresh_loop):
        """Yazma tool'lari sirayla calismali (paralel degil)."""
        loop = fresh_loop
        execution_order = []

        async def tracked_exec(name, args):
            execution_order.append(name)
            return "ok"

        think_responses = [
            {
                "content": "",
                "tool_calls": [
                    {"id": "c1", "function": {"name": "write_file", "arguments": '{"path": "/a.txt", "content": "x"}'}},
                    {"id": "c2", "function": {"name": "patch", "arguments": '{"path": "/b.txt", "old_string": "x", "new_string": "y"}'}},
                ],
                "usage": {},
            },
            {
                "content": "done",
                "tool_calls": [],
                "usage": {},
            },
        ]
        loop.reasoning.think = AsyncMock(side_effect=think_responses)

        with patch("orchestrator.experimental_loop.executor.async_execute_json",
                   AsyncMock(side_effect=tracked_exec)):
            result = await loop.process("yaz")

        assert result == "done"
        # Write tools should run in order
        assert execution_order == ["write_file", "patch"]


# ── Test: Rate limiting ────────────────────────────────────────────────────


class TestRateLimiting:
    """3 tur/dk limiti."""

    @pytest.mark.asyncio
    async def test_rate_limit_cooldown_after_error(self, fresh_loop):
        """LLM hatasinda cooldown + recursion yapilmali, sistem cokmemeli."""
        loop = fresh_loop

        # Simulate an LLM error: every call raises RuntimeError
        mock_think = AsyncMock(side_effect=RuntimeError("API timeout"))
        loop.reasoning.think = mock_think

        with patch("asyncio.sleep", AsyncMock()):
            result = await loop.process("test")

        # After all retries exhausted, should get error-marker response
        assert isinstance(result, str)
        # _think catches RuntimeError and retries recursively up to 3 times
        # then returns {"content": "", "tool_calls": [], "finish_reason": "error"}
        # which triggers empty-response retry in process()
        # Eventually reaches MAX_LOOP_ITERATIONS
        assert "Maximum" in result


# ── Test: LRU cache ────────────────────────────────────────────────────────


class TestLRUCache:
    """Ayni sorgu cache'ten gelmeli."""

    @pytest.mark.asyncio
    async def test_same_query_not_cached_as_llm_response(self, fresh_loop):
        """LLM yaniti cache'lenmez, her seferinde LLM cagrilir."""
        loop = fresh_loop
        mock_think = AsyncMock(return_value={
            "content": "Cevap bu.",
            "tool_calls": [],
            "usage": {"prompt_tokens": 30, "completion_tokens": 5},
        })
        loop.reasoning.think = mock_think

        await loop.process("nedir bu?")
        await loop.process("nedir bu?")

        # LLM her seferinde cagrilmali (LLM response caching yok)
        assert mock_think.call_count == 2

    @pytest.mark.asyncio
    async def test_read_file_cache(self, fresh_loop):
        """read_file sonucu cache'lenmeli ve 2. okumada executor cagrilmamali."""
        loop = fresh_loop

        think_responses = [
            {
                "content": "",
                "tool_calls": [{
                    "id": "c1",
                    "function": {"name": "read_file", "arguments": '{"path": "/tmp/test.txt"}'},
                }],
                "usage": {},
            },
            {
                "content": "",
                "tool_calls": [{
                    "id": "c2",
                    "function": {"name": "read_file", "arguments": '{"path": "/tmp/test.txt"}'},
                }],
                "usage": {},
            },
            {
                "content": "done",
                "tool_calls": [],
                "usage": {},
            },
        ]
        loop.reasoning.think = AsyncMock(side_effect=think_responses)

        executor_call_count = 0

        async def tracked_exec(name, args):
            nonlocal executor_call_count
            executor_call_count += 1
            return "file content"

        with patch("orchestrator.experimental_loop.executor.async_execute_json",
                   AsyncMock(side_effect=tracked_exec)):
            result = await loop.process("oku")

        assert result == "done"
        # Executor should only be called once for the same file
        assert executor_call_count == 1


# ── Test: Error recovery ───────────────────────────────────────────────────


class TestErrorRecovery:
    """Tool hatasinda retry mekanizmasi."""

    @pytest.mark.asyncio
    async def test_tool_error_handled_gracefully(self, fresh_loop):
        """Tool hatasi sistemin cokmesine yol acmamali."""
        loop = fresh_loop

        # First call returns a tool call that will fail, second returns response
        think_responses = [
            {
                "content": "",
                "tool_calls": [{
                    "id": "c1",
                    "function": {"name": "read_file", "arguments": '{"path": "/nonexistent.txt"}'},
                }],
                "usage": {},
            },
            {
                "content": "That file does not exist.",
                "tool_calls": [],
                "usage": {},
            },
        ]
        loop.reasoning.think = AsyncMock(side_effect=think_responses)

        with patch("orchestrator.experimental_loop.executor.async_execute_json",
                   AsyncMock(side_effect=FileNotFoundError("No such file"))):
            result = await loop.process("oku")

        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_empty_tool_streak_forces_direct_answer(self, fresh_loop):
        """3+ bos/error tool sonucu → zorla yanit ver."""
        loop = fresh_loop

        # Return 3 tool calls that produce empty/error results
        think_responses = []
        for i in range(4):
            think_responses.append({
                "content": "",
                "tool_calls": [{
                    "id": f"c{i}",
                    "function": {"name": "search_files", "arguments": '{"pattern": "xyz"}'},
                }],
                "usage": {},
            })
        # Final response
        think_responses.append({
            "content": "Based on what I know, here's the answer.",
            "tool_calls": [],
            "usage": {},
        })
        loop.reasoning.think = AsyncMock(side_effect=think_responses)

        with patch("orchestrator.experimental_loop.executor.async_execute_json",
                   AsyncMock(return_value="error: not found")):
            result = await loop.process("ara")

        assert "Based on" in result

    @pytest.mark.asyncio
    async def test_truncated_response_continues(self, fresh_loop):
        """finish_reason=length durumunda loop devam etmeli."""
        loop = fresh_loop

        think_responses = [
            {
                "content": "Kesik cevap",
                "tool_calls": [],
                "finish_reason": "length",
                "usage": {},
            },
            {
                "content": "Devam eden cevap",
                "tool_calls": [],
                "usage": {},
            },
        ]
        loop.reasoning.think = AsyncMock(side_effect=think_responses)

        result = await loop.process("anlat")

        assert result == "Devam eden cevap"
