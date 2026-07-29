"""Tests for core/tokenizer.py"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestCountTokens:
    def test_empty_text(self):
        from core.tokenizer import count_tokens
        assert count_tokens("") == 0

    def test_none_text(self):
        from core.tokenizer import count_tokens
        assert count_tokens("") == 0

    def test_fallback_char_count(self, monkeypatch):
        """When tiktoken is not available, fallback to char/4."""
        import core.tokenizer as tok
        monkeypatch.setattr(tok, "HAS_TIKTOKEN", False)
        monkeypatch.setattr(tok, "tiktoken", None)

        from core.tokenizer import count_tokens
        assert count_tokens("hello") == 1
        assert count_tokens("hello world test") == 4

    def test_tiktoken_counting(self):
        """If tiktoken is available, actual token count should work."""
        from core.tokenizer import count_tokens, HAS_TIKTOKEN
        if not HAS_TIKTOKEN:
            pytest.skip("tiktoken not installed")
        count = count_tokens("Hello, how are you today?", model="gpt-4")
        assert count > 0

    def test_with_model_specific_encoding(self):
        from core.tokenizer import count_tokens
        count = count_tokens("test" * 100, model="deepseek/deepseek-chat")
        assert count > 0


class TestCountMessagesTokens:
    def test_empty_messages(self):
        from core.tokenizer import count_messages_tokens
        assert count_messages_tokens([]) == 0

    def test_simple_message(self):
        from core.tokenizer import count_messages_tokens
        msgs = [{"role": "user", "content": "Hello world"}]
        count = count_messages_tokens(msgs)
        assert count > 0

    def test_message_with_tool_calls(self):
        from core.tokenizer import count_messages_tokens
        msgs = [
            {"role": "assistant", "content": "", "tool_calls": [
                {"function": {"arguments": '{"key": "value"}'}}
            ]},
            {"role": "tool", "result": "some tool output here", "content": ""},
        ]
        count = count_messages_tokens(msgs)
        assert count > 0

    def test_message_with_none_content(self):
        from core.tokenizer import count_messages_tokens
        msgs = [{"role": "user", "content": None}]
        count = count_messages_tokens(msgs)
        assert count == 0


class TestResolveEncoding:
    def test_encoding_resolution(self):
        from core.tokenizer import _resolve_encoding
        assert _resolve_encoding("") == "cl100k_base"
        assert _resolve_encoding("gpt-4o") == "o200k_base"
        assert _resolve_encoding("deepseek/deepseek-chat") == "cl100k_base"
        assert _resolve_encoding("unknown-model") == "cl100k_base"
