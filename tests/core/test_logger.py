"""Tests for core/logger.py"""
import pytest
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestLoggerSetup:
    def test_logger_creation(self):
        from core.logger import setup_logging
        logger = setup_logging()
        assert logger.name == "dorina"
        assert logger.level > 0

    def test_logger_is_singleton(self):
        from core.logger import setup_logging
        logger1 = setup_logging()
        logger2 = setup_logging()
        assert logger1 is logger2

    def test_logger_has_handlers(self):
        from core.logger import setup_logging
        logger = setup_logging()
        assert len(logger.handlers) > 0


class TestSessionContext:
    def test_set_and_clear_session(self):
        from core.logger import set_session_context, clear_session_context, _get_session_tag
        clear_session_context()
        tag = _get_session_tag()
        assert tag == ""

        set_session_context("abc123")
        tag = _get_session_tag()
        assert "abc123" in tag
        assert "[" in tag

        clear_session_context()
        tag = _get_session_tag()
        assert tag == ""

    def test_session_thread_isolation(self):
        """Session context should be thread-local."""
        from core.logger import set_session_context, clear_session_context, _get_session_tag
        import threading

        results = []

        def worker():
            set_session_context("thread_session")
            tag = _get_session_tag()
            results.append(tag)

        clear_session_context()
        t = threading.Thread(target=worker)
        t.start()
        t.join()

        main_tag = _get_session_tag()
        assert main_tag == ""
        assert len(results) == 1
        # session_id is truncated to 12 chars
        assert "[thread_sessi" in results[0] or "thread_session" in results[0]


class TestRedactingFormatter:
    def test_formatter_redacts_keys(self):
        from core.logger import RedactingFormatter
        import logging

        fmt = RedactingFormatter("%(message)s")
        record = logging.LogRecord(
            name="test", level=logging.INFO,
            pathname="", lineno=0, msg="API key=sk-or-v1-abcdefghijklmnopqrstuvwxyz123456",
            args=(), exc_info=None,
        )
        output = fmt.format(record)
        assert "***" in output

    def test_formatter_normal_messages(self):
        from core.logger import RedactingFormatter
        import logging

        fmt = RedactingFormatter("%(message)s")
        record = logging.LogRecord(
            name="test", level=logging.INFO,
            pathname="", lineno=0, msg="Hello world, all good!",
            args=(), exc_info=None,
        )
        output = fmt.format(record)
        assert "Hello world" in output


class TestQuietThirdParty:
    def test_quiet_loggers(self):
        from core.logger import _quiet_third_party_loggers
        import logging

        _quiet_third_party_loggers()
        for name in ("httpx", "httpcore", "openai", "urllib3"):
            logger = logging.getLogger(name)
            assert logger.level >= logging.WARNING
