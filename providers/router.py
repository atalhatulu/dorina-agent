"""
Provider router — reads active provider/model from config, resolves API key.
All provider metadata lives in ~/.dorina/providers.json (single source of truth).
"""
from __future__ import annotations
import os
from typing import Optional

from core.config import settings
from providers.keys import keys


# Provider name mapping for litellm
PROVIDER_MAP = {
    "google": "gemini",
    "gemini": "gemini",
    "openai": "openai",
    "anthropic": "anthropic",
    "deepseek": "deepseek",
    "groq": "groq",
    "openrouter": "openrouter",
    "mistral": "mistral",
    "xai": "xai",
    "ollama": "ollama",
    "fireworks": "fireworks",
    "deepinfra": "deepinfra",
    "together": "together",
    "huggingface": "huggingface",
    "perplexity": "perplexity",
    "replicate": "replicate",
    "cohere": "cohere",
    "siliconflow": "siliconflow",
    "nvidia": "nvidia",
    "novita": "novita",
    "qwen": "qwen",
    "minimax": "minimax",
}

# ── Direct HTTP providers (bypass liteLLM) ──
_DIRECT_PROVIDERS: set[str] = {"deepseek"}


class ProviderRouter:
    """Routes to the active provider/model from config."""

    def __init__(self):
        self._current = 0

    def get_active(self) -> dict:
        """Return provider info from config + resolved API key."""
        provider = settings.model.provider
        model = settings.model.default
        api_key = keys.get_key(provider) or os.environ.get(f"{provider.upper()}_API_KEY", "")

        # Normalize provider name for litellm
        litellm_provider = PROVIDER_MAP.get(provider, provider)
        return {
            "name": litellm_provider,
            "model": model,
            "api_key": api_key,
        }

    def get_transport_mode(self) -> dict:
        """Return transport routing info for the current provider.

        Returns:
            Dict with:
              - mode: "direct" | "litellm"
              - provider: provider name
              - model: full model string
              - api_key: resolved API key or ""
        """
        provider = settings.model.provider
        model = settings.model.default

        if provider in _DIRECT_PROVIDERS:
            return {
                "mode": "direct",
                "provider": provider,
                "model": model,
                "api_key": keys.get_key(provider) or os.environ.get(f"{provider.upper()}_API_KEY", ""),
            }

        return {
            "mode": "litellm",
            "provider": provider,
            "model": model,
            "api_key": keys.get_key(provider) or os.environ.get(f"{provider.upper()}_API_KEY", ""),
        }

    def is_direct_mode(self) -> bool:
        """Check if current provider uses direct HTTP (bypass liteLLM)."""
        return settings.model.provider in _DIRECT_PROVIDERS

    def get_model_string(self) -> str:
        """Return litellm-format model string (e.g. gemini/gemini-2.5-flash-lite)."""
        from core.model_utils import build_model_string
        active = self.get_active()
        return build_model_string(active["name"], active["model"])

    def get_active_model(self) -> str:
        return settings.model.default

    def get_active_provider(self) -> str:
        return settings.model.provider

    def reset(self):
        self._current = 0

    def select_provider(self, messages: list, tool_count: int = 0) -> str:
        return settings.model.default


router = ProviderRouter()
