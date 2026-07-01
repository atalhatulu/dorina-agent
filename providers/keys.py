"""Key manager — single source of truth: ~/.dorina/providers.json.

All provider metadata, API keys, and model lists live in providers.json.
.env files are optional overrides for development/debugging.
"""
from __future__ import annotations
import json
import os
from pathlib import Path

from core.constants import DORINA_HOME

PROVIDERS_FILE = DORINA_HOME / "providers.json"

# ── Hardcoded metadata fallback (sadece providers.json yoksa) ──
_DEFAULT_PROVIDERS: dict[str, dict] = {
    "google": {
        "url": "https://generativelanguage.googleapis.com/v1beta",
        "models": ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.5-pro"],
        "display": "Google Gemini",
        "needs_key": True,
    },
    "deepseek": {
        "url": "https://api.deepseek.com",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "display": "DeepSeek",
        "needs_key": True,
    },
    "openrouter": {
        "url": "https://openrouter.ai/api/v1",
        "models": ["openai/gpt-4o-mini", "google/gemma-4-31b-it"],
        "display": "OpenRouter",
        "needs_key": True,
    },
    "openai": {
        "url": "https://api.openai.com/v1",
        "models": ["gpt-4o-mini", "gpt-4o"],
        "display": "OpenAI",
        "needs_key": True,
    },
    "anthropic": {
        "url": "https://api.anthropic.com/v1",
        "models": ["claude-sonnet-4"],
        "display": "Anthropic",
        "needs_key": True,
    },
    "groq": {
        "url": "https://api.groq.com/openai/v1",
        "models": ["llama-3.3-70b-versatile"],
        "display": "Groq",
        "needs_key": True,
    },
}

ENV_MAP: dict[str, str] = {
    "deepseek": "DEEPSEEK_API_KEY",
    "google": "GOOGLE_API_KEY",
    "gemini": "GOOGLE_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "xai": "XAI_API_KEY",
    "cohere": "COHERE_API_KEY",
    "perplexity": "PERPLEXITY_API_KEY",
    "fireworks": "FIREWORKS_API_KEY",
    "replicate": "REPLICATE_API_KEY",
    "huggingface": "HF_API_KEY",
    "together": "TOGETHER_API_KEY",
    "siliconflow": "SILICONFLOW_API_KEY",
    "deepinfra": "DEEPINFRA_API_KEY",
    "nvidia": "NVIDIA_API_KEY",
    "novita": "NOVITA_API_KEY",
    "qwen": "QWEN_API_KEY",
    "minimax": "MINIMAX_API_KEY",
    "ollama": "",
}


def _load_providers() -> dict[str, dict]:
    """Load all provider metadata from providers.json."""
    if not PROVIDERS_FILE.exists():
        return dict(_DEFAULT_PROVIDERS)
    try:
        raw = json.loads(PROVIDERS_FILE.read_text())
        provs = raw.get("providers", {})
        if provs:
            return provs
        return dict(_DEFAULT_PROVIDERS)
    except (json.JSONDecodeError, OSError):
        return dict(_DEFAULT_PROVIDERS)


def _load_default() -> str:
    """Load default model string from providers.json."""
    if not PROVIDERS_FILE.exists():
        return ""
    try:
        raw = json.loads(PROVIDERS_FILE.read_text())
        return raw.get("default", "")
    except (json.JSONDecodeError, OSError):
        return ""


PROVIDERS: dict[str, dict] = _load_providers()
DEFAULT_MODEL: str = _load_default()


class KeyManager:
    """Manages API keys from providers.json + env overrides."""

    def __init__(self):
        self._keys: dict[str, str] = {}
        self._load()

    def _load(self):
        """Load keys: providers.json > .env (override)."""
        # 1. providers.json'daki api_key'ler
        for name, info in PROVIDERS.items():
            ak = info.get("api_key", "")
            if ak:
                self._keys[name] = ak
                # env'e de yaz (litellm/tools icin)
                ev = ENV_MAP.get(name, "")
                if ev and not os.getenv(ev):
                    os.environ[ev] = ak

        # 2. .env override'lari
        self._load_dotenv()
        for name, ev in ENV_MAP.items():
            if ev and os.getenv(ev):
                self._keys[name] = os.getenv(ev)

    def _load_dotenv(self):
        """Optional .env overrides in ~/.dorina/.env."""
        env_file = DORINA_HOME / ".env"
        if not env_file.exists():
            return
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip()
            if len(v) > 1 and v[0] == v[-1] and v[0] in ('"', "'"):
                v = v[1:-1]
            if k and v and k not in os.environ:
                os.environ[k] = v

    def get_key(self, provider: str) -> str:
        return self._keys.get(provider, "") or os.getenv(ENV_MAP.get(provider, ""), "")

    def has_key(self, provider: str) -> bool:
        return bool(self.get_key(provider))

    def list_providers(self) -> list[tuple[str, str]]:
        """Return [(provider_id, display_name), ...] for all known providers."""
        result = []
        for pid, info in PROVIDERS.items():
            display = info.get("display", pid.title())
            result.append((pid, display))
        return result

    def get_provider_info(self, provider: str) -> dict | None:
        """Return full info dict for a provider, or None."""
        return PROVIDERS.get(provider)

    def get_models(self, provider: str) -> list[str]:
        """Return model list for a provider."""
        info = PROVIDERS.get(provider, {})
        return info.get("models", [])

    def save_key(self, provider: str, key: str):
        """Save API key for a provider — persists to providers.json + sets env."""
        self._keys[provider] = key

        # Write to providers.json
        if PROVIDERS_FILE.exists():
            try:
                raw = json.loads(PROVIDERS_FILE.read_text())
                raw.setdefault("providers", {}).setdefault(provider, {})["api_key"] = key
                PROVIDERS_FILE.write_text(json.dumps(raw, indent=2, ensure_ascii=False))
            except (json.JSONDecodeError, OSError):
                pass

        # Also set in env for runtime
        ev = ENV_MAP.get(provider, "")
        if ev:
            os.environ[ev] = key

    def delete_key(self, provider: str):
        """Remove API key for a provider."""
        self._keys.pop(provider, None)
        if PROVIDERS_FILE.exists():
            try:
                raw = json.loads(PROVIDERS_FILE.read_text())
                prov = raw.get("providers", {}).get(provider, {})
                prov.pop("api_key", None)
                PROVIDERS_FILE.write_text(json.dumps(raw, indent=2, ensure_ascii=False))
            except (json.JSONDecodeError, OSError):
                pass
        ev = ENV_MAP.get(provider, "")
        if ev:
            os.environ.pop(ev, None)

    def switch_to(self, provider: str, model: str | None = None):
        """Switch active provider and optionally model. Persists to config.yaml + providers.json."""
        from core.config import settings

        if model is None:
            models = self.get_models(provider)
            model = models[0] if models else "unknown"

        model_str = f"{provider}/{model}" if "/" not in model else model

        settings.model.provider = provider
        settings.model.default = model_str
        settings.save()

        # Also update providers.json default
        if PROVIDERS_FILE.exists():
            try:
                raw = json.loads(PROVIDERS_FILE.read_text())
                raw["default"] = model_str
                PROVIDERS_FILE.write_text(json.dumps(raw, indent=2, ensure_ascii=False))
            except (json.JSONDecodeError, OSError):
                pass


keys = KeyManager()
