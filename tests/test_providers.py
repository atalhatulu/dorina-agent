"""Tests for provider router — simplified: always reads from config."""
import pytest


class TestProviderRouter:
    def test_get_active_returns_dict(self):
        """Router should return a dict with name, model, api_key keys."""
        from providers.router import ProviderRouter
        r = ProviderRouter()
        active = r.get_active()
        assert isinstance(active, dict)
        assert "name" in active
        assert "model" in active
        assert "api_key" in active

    def test_get_model_string(self):
        """Should return a provider/model string."""
        from providers.router import ProviderRouter
        r = ProviderRouter()
        model_str = r.get_model_string()
        assert "/" in model_str
        assert model_str.count("/") == 1

    def test_get_active_model(self):
        """Should return a non-empty model string."""
        from providers.router import ProviderRouter
        r = ProviderRouter()
        model = r.get_active_model()
        assert isinstance(model, str)
        assert len(model) > 0

    def test_get_active_provider(self):
        """Should return a non-empty provider string."""
        from providers.router import ProviderRouter
        r = ProviderRouter()
        provider = r.get_active_provider()
        assert isinstance(provider, str)
        assert len(provider) > 0

    def test_select_provider_no_messages(self):
        """select_provider should return default model even with empty input."""
        from providers.router import ProviderRouter
        r = ProviderRouter()
        result = r.select_provider(messages=[], tool_count=0)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_select_provider_with_messages(self):
        """select_provider should return default model regardless of input complexity."""
        from providers.router import ProviderRouter
        r = ProviderRouter()
        result = r.select_provider(
            messages=[{"role": "user", "content": "test"}],
            tool_count=5,
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_reset_does_not_raise(self):
        """reset should be a no-op (kept for backward compatibility)."""
        from providers.router import ProviderRouter
        r = ProviderRouter()
        r.reset()  # Should not raise
