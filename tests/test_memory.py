"""Bellek modülü testleri."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestWorkingMemory:
    def test_add_and_count(self):
        from memory.working import WorkingMemory
        wm = WorkingMemory(max_messages=5)
        wm.add("user", "merhaba")
        wm.add("assistant", "selam")
        assert wm.count == 2

    def test_max_messages(self):
        from memory.working import WorkingMemory
        wm = WorkingMemory(max_messages=3)
        wm.add("user", "1")
        wm.add("assistant", "2")
        wm.add("user", "3")
        wm.add("assistant", "4")
        assert wm.count == 3  # max'ta kalmalı

    def test_clear(self):
        from memory.working import WorkingMemory
        wm = WorkingMemory()
        wm.add("user", "test")
        wm.clear()
        assert wm.count == 0


class TestEpisodicMemory:
    def test_save_and_search(self):
        from memory.episodic import EpisodicMemory
        em = EpisodicMemory()
        em.save_memory("test_key", "test_value", "test")
        results = em.search_memories("test_value")
        assert len(results) >= 1
        assert results[0]["key"] == "test_key"

    def test_save_and_load_session(self):
        from memory.episodic import EpisodicMemory
        em = EpisodicMemory()
        em.save_session("test123", "Test Session",
                        [{"role": "user", "content": "selam"}], "özet")
        session = em.load_session("test123")
        assert session is not None
        assert session["title"] == "Test Session"
        assert len(session["messages"]) == 1
        em.delete_session("test123")
        assert em.load_session("test123") is None
