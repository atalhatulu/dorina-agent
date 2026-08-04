"""Tests for smart tool result retention in Context."""

import pytest
from orchestrator.context import Context, _decide_result_policy

def test_read_file_retention():
    """read_file hiç kesilmez."""
    c = Context()
    long_data = "A" * 10000
    c.add_tool_result("read_file", long_data)
    messages = c.get_messages()
    assert long_data in messages[0]["content"]
    assert "truncated" not in messages[0]["content"]

def test_web_search_error():
    """Büyük web_search içinde error geçiyorsa preview (4000 limit, ilk+son)."""
    c = Context()
    # If error is at the end, the 'preview' policy keeps first 2000 and last 2000.
    # Total limit 4000. So we need a 10000 char string with 'error' near the end.
    long_data = "A" * 8000 + " kritik error detaylari " + "B" * 1000
    c.add_tool_result("web_search", long_data)
    messages = c.get_messages()
    
    # 10000 is > 4000, so it gets truncated
    assert "truncated" in messages[0]["content"]
    # But because it's preview, the last 2000 chars are kept!
    assert "kritik error detaylari" in messages[0]["content"]

def test_terminal_traceback():
    """terminal traceback içeriyorsa limit 4000 (preview)."""
    c = Context()
    long_data = "A" * 3000 + "Traceback (most recent call last):\n..." + "B" * 500
    c.add_tool_result("terminal", long_data)
    messages = c.get_messages()
    
    # It shouldn't be truncated because limit is 4000 and total length is ~3550
    assert "truncated" not in messages[0]["content"]
    assert "Traceback" in messages[0]["content"]

def test_terminal_normal_truncate():
    """terminal normal uzun çıktı -> 1500 limiti."""
    c = Context()
    long_data = "A" * 3000
    c.add_tool_result("terminal", long_data)
    messages = c.get_messages()
    
    assert "truncated" in messages[0]["content"]
    # Limit is 1500, but wait, the content adds `[terminal] -> `
    # Length of `messages[0]["content"]` should be around 1500 + length of `... (truncated` part
    assert len(messages[0]["content"]) < 2000

def test_json_success_full():
    """Kısa JSON {"status":"ok"} (<=800) tam saklanır."""
    c = Context()
    json_data = '{"status": "ok", "records_updated": 42}'
    c.add_tool_result("db_tool", json_data)
    messages = c.get_messages()
    
    assert "truncated" not in messages[0]["content"]
    assert json_data in messages[0]["content"]

def test_count_messages_tokens_regression():
    """count_messages_tokens bozulmamalı."""
    from core.tokenizer import count_messages_tokens
    c = Context()
    c.add_tool_result("web_search", "A" * 100)
    tokens = count_messages_tokens(c.get_messages())
    assert tokens > 0
