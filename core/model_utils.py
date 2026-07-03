"""Model string utilities — litellm-format model string generation.

All provider/model → "provider/model" conversions happen in one place.
litellm special cases:
  - google/gemini providers → "gemini/" prefix (litellm convention)
  - openrouter → "openrouter/" prefix
  - Model strings already containing "/" are passed through as-is.
"""


def build_model_string(provider: str, model: str) -> str:
    """Build litellm-compatible model string from provider and model name.

    Handles special provider prefixes:
      - google/gemini → gemini/  (litellm uses "gemini/" not "google/")
      - openrouter    → openrouter/
      - everything else → {provider_lower}/

    Args:
        provider: Provider name (e.g. "google", "openai", "openrouter")
        model: Model name (e.g. "gemini-2.5-flash", "gpt-4o")

    Returns:
        litellm-format model string (e.g. "gemini/gemini-2.5-flash", "openai/gpt-4o")
    """
    if not provider:
        return model

    provider_lower = provider.lower().strip()

    # litellm uses "gemini/" for Google models, not "google/"
    if provider_lower in ("google", "gemini"):
        # Strip any existing google/ or gemini/ prefix
        raw = model.split("/", 1)[-1] if "/" in model else model
        return f"gemini/{raw}"

    # Already has provider prefix — pass through
    if "/" in model:
        return model

    # openrouter prefix
    if provider_lower == "openrouter":
        return f"openrouter/{model}"

    return f"{provider_lower}/{model}"
