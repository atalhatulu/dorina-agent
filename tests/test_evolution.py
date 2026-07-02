"""Tests for evolution module — review, self-calibration, learning."""
import pytest
import json
from pathlib import Path


class TestReview:
    def test_review_disabled(self):
        """Self-review kaldirildi, run_review bos string doner."""
        from evolution.self_check import run_review
        import asyncio
        result = asyncio.run(run_review("test code", trigger="manual"))
        assert result == ""


class TestLearning:
    def setup_method(self):
        self.learnings_file = Path(__file__).parent.parent.parent / "data" / "learnings.json"
        self.backup = None
        if self.learnings_file.exists():
            self.backup = self.learnings_file.read_text()

    def teardown_method(self):
        if self.backup is not None:
            self.learnings_file.write_text(self.backup)
        elif self.learnings_file.exists():
            self.learnings_file.unlink()

    def test_log_and_get_learning(self):
        """log_learning + get_relevant_learnings should roundtrip."""
        from evolution.self_check import log_learning, get_relevant_learnings

        log_learning("dosya okuma testi", "dosya bulunamadi", "path duzeltildi")
        result = get_relevant_learnings("dosya okuma islemi")
        assert "testi" in result
        assert "bulunamadi" in result

    def test_get_learning_no_file(self):
        """get_relevant_learnings with no file should return empty string."""
        from evolution.self_check import get_relevant_learnings
        if self.learnings_file.exists():
            self.learnings_file.unlink()
        result = get_relevant_learnings("anything")
        assert result == ""

    def test_log_learning_corrupted_file(self):
        """log_learning should handle corrupted file gracefully."""
        from evolution.self_check import log_learning, get_relevant_learnings
        self.learnings_file.parent.mkdir(parents=True, exist_ok=True)
        self.learnings_file.write_text("not valid json")
        log_learning("test", "fail", "ok")  # should not crash
        result = get_relevant_learnings("test")
        assert isinstance(result, str)
