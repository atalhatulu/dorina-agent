"""Streaming tests — _think_stream accumulator + callback mechanism."""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


@pytest.mark.asyncio
async def test_think_stream_content_chunks():
    """Test that content chunks are accumulated and callbacks fire."""
    from orchestrator.reasoning import ReasoningEngine
    engine = ReasoningEngine()

    collected = []

    async def mock_stream():
        class MockDelta:
            content = "Mer"
            tool_calls = None
        class MockChoice:
            delta = MockDelta()
            finish_reason = None
        class MockChunk:
            choices = [MockChoice()]
        yield MockChunk()

        class MockDelta2:
            content = "haba"
            tool_calls = None
        class MockChoice2:
            delta = MockDelta2()
            finish_reason = None
        class MockChunk2:
            choices = [MockChoice2()]
        yield MockChunk2()

        class MockDelta3:
            content = "!"
            tool_calls = None
        class MockChoice3:
            delta = MockDelta3()
            finish_reason = "stop"
        class MockChunk3:
            choices = [MockChoice3()]
        yield MockChunk3()

    class MockLLM:
        async def acompletion(self, stream=True, **params):
            assert stream is True
            return mock_stream()

    def callback(chunk: str):
        collected.append(chunk)

    result = await engine._think_stream(MockLLM(), {"model": "test"}, callback)

    assert result["content"] == "Merhaba!"
    assert result["finish_reason"] == "stop"
    assert result["_streamed"] is True
    assert "".join(collected) == "Merhaba!"


@pytest.mark.asyncio
async def test_think_stream_tool_calls():
    """Test that tool call deltas are accumulated correctly."""
    from orchestrator.reasoning import ReasoningEngine
    engine = ReasoningEngine()

    async def mock_stream():
        class MockTCDelta1:
            index = 0
            id = "call_1"
            function = type("obj", (), {"name": "read_", "arguments": ""})()

        class MockDelta1:
            content = None
            tool_calls = [MockTCDelta1()]
        class MockChoice1:
            delta = MockDelta1()
            finish_reason = None
        class MockChunk1:
            choices = [MockChoice1()]
        yield MockChunk1()

        class MockTCDelta2:
            index = 0
            id = ""
            function = type("obj", (), {"name": "file", "arguments": "{\"pat"})()
        class MockDelta2:
            content = None
            tool_calls = [MockTCDelta2()]
        class MockChoice2:
            delta = MockDelta2()
            finish_reason = None
        class MockChunk2:
            choices = [MockChoice2()]
        yield MockChunk2()

        class MockTCDelta3:
            index = 0
            id = ""
            function = type("obj", (), {"name": "", "arguments": "h\": \"test\"}"})()
        class MockDelta3:
            content = None
            tool_calls = [MockTCDelta3()]
        class MockChoice3:
            delta = MockDelta3()
            finish_reason = "tool_calls"
        class MockChunk3:
            choices = [MockChoice3()]
        yield MockChunk3()

    class MockLLM:
        async def acompletion(self, stream=True, **params):
            return mock_stream()

    result = await engine._think_stream(MockLLM(), {"model": "test"}, lambda x: None)

    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["function"]["name"] == "read_file"
    assert "path" in result["tool_calls"][0]["function"]["arguments"]
    assert result["finish_reason"] == "tool_calls"


@pytest.mark.asyncio
async def test_think_stream_no_stream_arg():
    """Test that without stream_callback, normal acompletion is used."""
    from orchestrator.reasoning import ReasoningEngine
    engine = ReasoningEngine()

    class MockChoice:
        finish_reason = "stop"
        class MockMessage:
            content = "normal response"
            tool_calls = None
        message = MockMessage()

    class MockResponse:
        choices = [MockChoice()]
        class MockUsage:
            prompt_tokens = 10
            completion_tokens = 20
        usage = MockUsage()
        _cost = 0.001

    class MockLLM:
        async def acompletion(self, **params):
            assert "stream" not in params
            return MockResponse()

    original = engine._get_llm
    engine._get_llm = lambda: MockLLM()
    try:
        result = await engine.think("system", [{"role": "user", "content": "hi"}])
        assert result["content"] == "normal response"
    finally:
        engine._get_llm = original
