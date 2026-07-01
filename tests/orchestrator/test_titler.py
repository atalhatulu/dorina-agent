"""Tests for orchestrator/titler.py"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from orchestrator.titler import autotitle


class TestAutotitle:
    def test_basic_title(self):
        title = autotitle("bugun hava cok guzel")
        assert title == "bugun hava cok guzel"

    def test_title_truncated_to_60_chars(self):
        long_input = "a" * 100
        title = autotitle(long_input)
        assert len(title) == 60

    def test_empty_input_returns_empty(self):
        title = autotitle("")
        assert title == ""

    def test_whitespace_input_returns_empty(self):
        title = autotitle("   ")
        assert title == ""

    def test_none_input_returns_empty(self):
        title = autotitle(None)
        assert title == ""

    def test_title_strips_whitespace(self):
        title = autotitle("  merhaba dunya  ")
        assert title == "merhaba dunya"

    @patch("session.manager.manager")
    def test_with_session_id_calls_rename(self, mock_manager):
        mock_manager.current_id = "test-session"
        title = autotitle("kod cozumu", session_id="test-session")
        assert title == "kod cozumu"
        mock_manager.rename.assert_called_once_with("test-session", "kod cozumu")

    @patch("session.manager.manager")
    def test_with_session_id_rename_failure_does_not_raise(self, mock_manager):
        mock_manager.rename.side_effect = Exception("db error")
        title = autotitle("hata testi", session_id="test-session")
        assert title == "hata testi"

    def test_without_session_id_does_not_call_rename(self):
        title = autotitle("sadece baslik")
        assert title == "sadece baslik"

    def test_special_characters_preserved(self):
        title = autotitle("üç harf? harika!")
        assert title == "üç harf? harika!"
