"""Memory module tests."""

import pytest


class TestBaseMemory:
    """All memory types implement the common interface."""

    def test_all_implement_base(self):
        from memory.base import MemoryProtocol, BaseMemory
        from memory.working import WorkingMemory
        from memory.semantic import SemanticMemory
        from memory.episodic import EpisodicMemory
        from memory.procedural import ProceduralMemory

        assert isinstance(WorkingMemory(), BaseMemory)
        assert isinstance(SemanticMemory(), BaseMemory)
        assert isinstance(EpisodicMemory(), BaseMemory)
        assert isinstance(ProceduralMemory(), BaseMemory)

    def test_all_have_memory_type(self):
        from memory.base import BaseMemory
        from memory.working import WorkingMemory
        from memory.semantic import SemanticMemory
        from memory.episodic import EpisodicMemory
        from memory.procedural import ProceduralMemory

        assert WorkingMemory().memory_type == "working"
        assert SemanticMemory().memory_type == "semantic"
        assert EpisodicMemory().memory_type == "episodic"
        assert ProceduralMemory().memory_type == "procedural"

    def test_all_have_common_methods(self):
        from memory.working import WorkingMemory
        from memory.semantic import SemanticMemory
        from memory.episodic import EpisodicMemory
        from memory.procedural import ProceduralMemory

        for cls in [WorkingMemory, SemanticMemory, EpisodicMemory, ProceduralMemory]:
            inst = cls()
            assert hasattr(inst, "add")
            assert hasattr(inst, "get")
            assert hasattr(inst, "search")
            assert hasattr(inst, "delete")
            assert hasattr(inst, "clear")
            assert hasattr(inst, "count")


class TestWorkingMemory:
    def test_add_and_count(self):
        from memory.working import WorkingMemory
        wm = WorkingMemory(max_messages=5)
        wm.add("user", "merhaba")
        wm.add("assistant", "selam")
        assert wm.count() == 2

    def test_max_messages(self):
        from memory.working import WorkingMemory
        wm = WorkingMemory(max_messages=3)
        wm.add("user", "1")
        wm.add("assistant", "2")
        wm.add("user", "3")
        wm.add("assistant", "4")
        assert wm.count() == 3  # max'ta kalmalı

    def test_clear(self):
        from memory.working import WorkingMemory
        wm = WorkingMemory()
        wm.add("user", "test")
        wm.clear()
        assert wm.count() == 0


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
