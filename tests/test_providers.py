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

    @pytest.mark.asyncio
    async def test_fallback(self):
        """Fallback should move to next provider."""
        from providers.router import ProviderRouter
        r = ProviderRouter()
        r.add_provider("first", "model-a", weight=1)
        r.add_provider("second", "model-b", weight=2)

        next_p = await r.fallback()
        assert next_p is not None
        assert next_p["name"] == "second"

        # No more providers
        exhausted = await r.fallback()
        assert exhausted is None

    @pytest.mark.asyncio
    async def test_fallback_exhausted(self):
        """Fallback after all providers exhausted should return None."""
        from providers.router import ProviderRouter
        r = ProviderRouter()
        r.add_provider("only", "model-o", weight=1)

        await r.fallback()  # exhaust
        result = await r.fallback()
        assert result is None

    @pytest.mark.asyncio
    async def test_reset(self):
        """Reset should go back to first provider."""
        from providers.router import ProviderRouter
        r = ProviderRouter()
        r.add_provider("a", "m1", weight=1)
        r.add_provider("b", "m2", weight=2)

        await r.fallback()
        r.reset()
        current = r.get_current()
        assert current["name"] == "a"

    def test_list(self):
        """List should return all providers with active status."""
        from providers.router import ProviderRouter
        r = ProviderRouter()
        r.add_provider("a", "m1", weight=1)
        r.add_provider("b", "m2", weight=2)

        providers = r.list()
        assert len(providers) == 2
        # Only the current one should be active
        assert providers[0]["active"] == True
        assert providers[1]["active"] == False

    @pytest.mark.asyncio
    async def test_fallback_with_error_logging(self):
        """Fallback should log the error and move to next."""
        from providers.router import ProviderRouter
        r = ProviderRouter()
        r.add_provider("a", "m1", weight=1)
        r.add_provider("b", "m2", weight=2)

        result = await r.fallback(error=ValueError("test error"))
        assert result is not None
        assert result["name"] == "b"
