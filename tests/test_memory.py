"""Memory module tests."""

try:
    import pytest
except ImportError:
    pytest = None


class TestBaseMemory:
    """All memory types implement the common interface."""

    def test_all_implement_base(self):
        from memory.base import MemoryProtocol, BaseMemory
        from memory.semantic import SemanticMemory
        from memory.episodic import EpisodicMemory
        from memory.procedural import ProceduralMemory

        assert isinstance(SemanticMemory(), BaseMemory)
        assert isinstance(EpisodicMemory(), BaseMemory)
        assert isinstance(ProceduralMemory(), BaseMemory)

    def test_all_have_memory_type(self):
        from memory.base import BaseMemory
        from memory.semantic import SemanticMemory
        from memory.episodic import EpisodicMemory
        from memory.procedural import ProceduralMemory

        assert SemanticMemory().memory_type == "semantic"
        assert EpisodicMemory().memory_type == "episodic"
        assert ProceduralMemory().memory_type == "procedural"

    def test_all_have_common_methods(self):
        from memory.semantic import SemanticMemory
        from memory.episodic import EpisodicMemory
        from memory.procedural import ProceduralMemory

        for cls in [SemanticMemory, EpisodicMemory, ProceduralMemory]:
            inst = cls()
            assert hasattr(inst, "add")
            assert hasattr(inst, "get")
            assert hasattr(inst, "search")
            assert hasattr(inst, "delete")
            assert hasattr(inst, "clear")
            assert hasattr(inst, "count")


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
        em.save_memory("test_key", "test_value", "test")
        assert em.get_memory("test_key") == "test_value"
        assert em.delete("test_key") is True
        assert em.get_memory("test_key") is None
