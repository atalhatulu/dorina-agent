"""Tests for core/error_db.py"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestErrorDB:
    def test_log_tool_error(self):
        from core.error_db import log_tool_error
        # Should not raise
        log_tool_error("test_tool", Exception("test error"), "call_123")
        log_tool_error("test_tool", None, message="direct message")

    def test_log_llm_error(self):
        from core.error_db import log_llm_error
        log_llm_error("test_provider", "test_model", Exception("LLM error"), 100)

    def test_log_system_error(self):
        from core.error_db import log_system_error
        log_system_error("test_component", Exception("system error"))

    def test_error_pattern_tracking(self):
        from core.error_db import log_error_pattern, get_frequent_patterns, clear_error_patterns
        # Record a pattern
        key = log_error_pattern("test_source", "ValueError", "bad value")
        assert "test_source|ValueError" in key

        # Record again (increment count)
        log_error_pattern("test_source", "ValueError", "bad value again")

        # Should be in frequent patterns (min_count=1)
        patterns = get_frequent_patterns(min_count=1)
        matching = [p for p in patterns if p["pattern_key"] == key]
        assert len(matching) >= 1
        assert matching[0]["count"] >= 2

        # Clear
        cleared = clear_error_patterns()
        assert cleared >= 0
        after = get_frequent_patterns(min_count=1)
        matching_after = [p for p in after if p["pattern_key"] == key]
        assert len(matching_after) == 0

    def test_error_db_unavailable(self, monkeypatch):
        """When DB is unavailable, functions should not raise."""
        import core.error_db as edb
        monkeypatch.setattr(edb, "_db_ok", False)

        from core.error_db import log_tool_error, log_llm_error, log_system_error, \
            log_error_pattern, get_frequent_patterns, clear_error_patterns

        log_tool_error("test", Exception("x"))
        log_llm_error("p", "m", Exception("x"), 10)
        log_system_error("c", Exception("x"))
        key = log_error_pattern("src", "TypeError", "msg")
        assert "src|TypeError" in key
        assert get_frequent_patterns() == []
        assert clear_error_patterns() == 0
