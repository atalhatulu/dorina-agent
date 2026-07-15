import pytest
import asyncio
from unittest.mock import patch, AsyncMock
from orchestrator.experimental_loop import AgentLoopV2, loop_v2

@pytest.mark.asyncio
async def test_loop_tool_timeout():
    # To test timeout, we mock async_execute_json to raise TimeoutError
    loop = AgentLoopV2()
    
    async def mock_exec(*args, **kwargs):
        raise asyncio.TimeoutError()

    with patch("orchestrator.experimental_loop.executor.async_execute_json", side_effect=mock_exec):
        tc = [{
            "id": "test_1",
            "function": {
                "name": "terminal",
                "arguments": '{"command": "sleep 100"}'
            }
        }]
        
        await loop._execute_tools(tc)
        
        # Check if context has error result for tool timeout
        last_msg = loop.context.get_messages()[-1]
        assert last_msg["role"] == "tool"
        assert "timeout" in last_msg["content"].lower()

@pytest.mark.asyncio
async def test_loop_repetition_guard(capsys):
    loop = AgentLoopV2()
    
    with patch("orchestrator.experimental_loop.executor.async_execute_json", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = "success"
        
        tc = [
            {
                "id": "t1",
                "function": {
                    "name": "web_search",
                    "arguments": '{"query": "test query"}'
                }
            },
            {
                "id": "t2",
                "function": {
                    "name": "web_search",
                    "arguments": '{"query": "test query"}'
                }
            }
        ]
        
        await loop._execute_tools(tc)
        
        # async_execute_json should only be called once because of the repetition guard
        assert mock_exec.call_count == 1
        
        out, _ = capsys.readouterr()
        assert "ayni argumanla tekrarliyor (test query), atlandi" in out

@pytest.mark.asyncio
async def test_loop_smart_escape():
    loop = AgentLoopV2()
    loop.context.add_user_message("test")
    
    # We will trigger the 3-error condition manually
    # Add fake errors to _error_patterns
    sig = "terminal:timeout"
    loop._error_patterns[sig] = [sig, 3] # 3 consecutive errors
    
    error_mock = Exception("Command timeout")
    
    with patch("orchestrator.experimental_loop.classify_api_error") as mock_classify:
        mock_classify.return_value.reason = "timeout"
        
        loop._handle_tool_error("terminal", error_mock, "t1")
        
        last_msg = loop.context.get_messages()[-1]
        assert last_msg["role"] == "user"
        assert "[SELF-REFLECTION]" in last_msg["content"]
        assert "zaman aşımına uğradı" in last_msg["content"]
