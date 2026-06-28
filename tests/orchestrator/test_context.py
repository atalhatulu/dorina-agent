"""Tests for orchestrator/context.py"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestContext:
    def test_initial_state(self, fresh_context):
        ctx = fresh_context
        assert ctx.messages == []
        assert ctx.message_count == 0

    def test_add_user_message(self, fresh_context):
        ctx = fresh_context
        ctx.add_user_message("Hello")
        assert len(ctx.messages) == 1
        assert ctx.messages[0]["role"] == "user"
        assert ctx.messages[0]["content"] == "Hello"

    def test_add_assistant_message(self, fresh_context):
        ctx = fresh_context
        ctx.add_assistant_message("Hi there")
        assert ctx.messages[0]["role"] == "assistant"
        assert ctx.messages[0]["content"] == "Hi there"

    def test_add_tool_result(self, fresh_context):
        ctx = fresh_context
        ctx.add_tool_result("read_file", "file contents", "call_123")
        assert ctx.messages[0]["role"] == "tool"
        assert ctx.messages[0]["name"] == "read_file"
        assert ctx.messages[0]["tool_call_id"] == "call_123"

    def test_add_tool_result_without_id(self, fresh_context):
        ctx = fresh_context
        ctx.add_tool_result("test_tool", "result")
        assert ctx.messages[0]["role"] == "tool"
        assert ctx.messages[0]["name"] == "test_tool"
        assert "tool_call_id" not in ctx.messages[0]

    def test_clear(self, fresh_context):
        ctx = fresh_context
        ctx.add_user_message("test")
        ctx.clear()
        assert ctx.message_count == 0
        assert ctx.estimated_tokens == 0

    def test_get_messages(self, fresh_context):
        ctx = fresh_context
        ctx.add_user_message("hi")
        ctx.add_assistant_message("hello")
        msgs = ctx.get_messages()
        assert len(msgs) == 2
        assert msgs is ctx.messages  # same reference

    def test_message_count(self, fresh_context):
        ctx = fresh_context
        assert ctx.message_count == 0
        ctx.add_user_message("one")
        assert ctx.message_count == 1
        ctx.add_user_message("two")
        assert ctx.message_count == 2

    def test_multiple_messages_sequence(self, fresh_context):
        ctx = fresh_context
        ctx.add_user_message("user1")
        ctx.add_assistant_message("assistant1")
        ctx.add_user_message("user2")
        assert len(ctx.messages) == 3
        assert ctx.messages[0]["role"] == "user"
        assert ctx.messages[1]["role"] == "assistant"
        assert ctx.messages[2]["role"] == "user"

    def test_tool_result_after_assistant(self, fresh_context):
        ctx = fresh_context
        # Simulate: assistant sends tool_calls, then tool results come back
        ctx.messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "test", "arguments": "{}"}}]
        })
        ctx.add_tool_result("test", "output", "call_1")
        assert len(ctx.messages) == 2
        assert ctx.messages[1]["role"] == "tool"
        assert ctx.messages[1]["tool_call_id"] == "call_1"

    def test_estimate_tokens(self, fresh_context):
        ctx = fresh_context
        ctx.add_user_message("a" * 100)
        tokens = ctx.estimate_tokens()
        assert tokens > 0
        assert ctx.estimated_tokens > 0
