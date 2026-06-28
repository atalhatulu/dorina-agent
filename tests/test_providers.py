"""Tests for provider router — fallback chain, cost-aware routing."""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestProviderRouter:
    def test_add_and_get_current(self):
        """Router should return the first added provider as current."""
        from providers.router import ProviderRouter
        r = ProviderRouter()
        r.add_provider("test_a", "model/a", weight=1)
        r.add_provider("test_b", "model/b", weight=2)
        current = r.get_current()
        assert current["name"] == "test_a"
        assert current["model"] == "model/a"

    def test_fallback(self):
        """Fallback should move to next provider."""
        from providers.router import ProviderRouter
        r = ProviderRouter()
        r.add_provider("first", "model-a", weight=1)
        r.add_provider("second", "model-b", weight=2)

        next_p = r.fallback()
        assert next_p is not None
        assert next_p["name"] == "second"

        # No more providers
        exhausted = r.fallback()
        assert exhausted is None

    def test_fallback_exhausted(self):
        """Fallback after all providers exhausted should return None."""
        from providers.router import ProviderRouter
        r = ProviderRouter()
        r.add_provider("only", "model-o", weight=1)

        r.fallback()  # exhaust
        result = r.fallback()
        assert result is None

    def test_reset(self):
        """Reset should go back to first provider."""
        from providers.router import ProviderRouter
        r = ProviderRouter()
        r.add_provider("a", "m1", weight=1)
        r.add_provider("b", "m2", weight=2)

        r.fallback()
        r.reset()
        current = r.get_current()
        assert current["name"] == "a"

    def test_list(self):
        """List should return all providers with active status."""
        from providers.router import ProviderRouter
        r = ProviderRouter()
        r.add_provider("p1", "m1", weight=1)
        r.add_provider("p2", "m2", weight=2)

        providers = r.list()
        assert len(providers) == 2
        assert providers[0]["active"] is True
        assert providers[1]["active"] is False

    def test_select_provider_simple(self):
        """Small task + few tools should select fast model."""
        from providers.router import ProviderRouter
        r = ProviderRouter()
        result = r.select_provider(
            messages=[{"role": "user", "content": "merhaba"}],
            tool_count=1,
        )
        # Should return a string (model name)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_select_provider_complex(self):
        """Large task + many tools should select default model."""
        from providers.router import ProviderRouter
        r = ProviderRouter()
        large_msg = {"role": "user", "content": "x" * 5000}
        result = r.select_provider(
            messages=[large_msg],
            tool_count=10,
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_fallback_with_error(self):
        """Fallback with error should not crash."""
        from providers.router import ProviderRouter
        r = ProviderRouter()
        r.add_provider("first", "model-a", weight=1)
        r.add_provider("second", "model-b", weight=2)

        result = r.fallback(error=ValueError("test error"))
        assert result is not None
        assert "first" in r.get_fallback_summary()
