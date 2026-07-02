"""LLM streaming interface for Gateway API.

Uses litellm for provider-agnostic streaming. Gets API keys
from the key manager. This module is imported by gateway/routes.py.
"""
from __future__ import annotations
import json
import os
from typing import AsyncGenerator


async def stream_chat(
    provider: str,
    model: str,
    messages: list[dict],
) -> AsyncGenerator[dict, None]:
    """Stream chat completions from a provider using litellm.

    Yields OpenAI-compatible chunk dicts:
        {"choices": [{"delta": {"content": "..."}}]}

    Args:
        provider: Provider name (e.g. "deepseek", "groq", "openai")
        model: Model name (e.g. "deepseek-chat", "gpt-4o-mini")
        messages: List of message dicts with "role" and "content"

    Yields:
        Chunk dicts following the streaming delta format.
    """
    # Try to get API key from key manager
    try:
        from providers.keys import keys as _key_mgr
        api_key = _key_mgr.get_key(provider)
    except ImportError:
        api_key = ""

    # Fall back to environment variable
    if not api_key:
        env_var = f"{provider.upper()}_API_KEY"
        api_key = os.environ.get(env_var, "")

    # Construct litellm model string (provider/model format)
    from core.model_utils import build_model_string
    model_name = build_model_string(provider, model)

    try:
        import litellm
        litellm.drop_params = True
        litellm.suppress_debug_info = True
        litellm.set_verbose = False
        litellm.telemetry = False

        params = {
            "model": model_name,
            "messages": messages,
            "stream": True,
        }
        if api_key:
            params["api_key"] = api_key

        response = await litellm.acompletion(**params)

        async for chunk in response:
            delta = chunk.choices[0].delta if chunk.choices else {}
            content = getattr(delta, "content", None)
            if content:
                yield {"choices": [{"delta": {"content": content}}]}

    except ImportError:
        yield {"choices": [{"delta": {"content": "Provider system not available: litellm not installed"}}]}
    except (TimeoutError, OSError, KeyError) as e:
        yield {"choices": [{"delta": {"content": f"Streaming error: {str(e)[:200]}"}}]}
