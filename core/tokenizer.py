"""Token estimator — tiktoken (varsa) veya litellm.get_model_info() ile token sayısı.

Fallback: tiktoken yoksa eski karakter/4 yöntemi kullanılır.
"""
from __future__ import annotations
from typing import Optional

# Try to import tiktoken; if not available, fall back
try:
    import tiktoken
    HAS_TIKTOKEN = True
except ImportError:
    HAS_TIKTOKEN = False
    tiktoken = None  # type: ignore

# ── Model → encoding name mapping (common models) ────────────────
MODEL_ENCODING_MAP: dict[str, str] = {
    # DeepSeek
    "deepseek/deepseek-chat": "cl100k_base",
    "deepseek/deepseek-v4-flash": "cl100k_base",
    "deepseek/deepseek-coder": "cl100k_base",
    # OpenAI
    "gpt-4": "cl100k_base",
    "gpt-4-turbo": "cl100k_base",
    "gpt-4o": "o200k_base",
    "gpt-4o-mini": "o200k_base",
    "gpt-3.5-turbo": "cl100k_base",
    "text-embedding-ada-002": "cl100k_base",
    "text-embedding-3-small": "cl100k_base",
    "text-embedding-3-large": "cl100k_base",
    # Groq (Llama-based, use cl100k as approximation)
    "groq/llama-3.3-70b-versatile": "cl100k_base",
    "groq/llama-3.1-8b-instant": "cl100k_base",
    "groq/llama-3.1-70b-versatile": "cl100k_base",
    "groq/mixtral-8x7b-32768": "cl100k_base",
    # OpenRouter (uses underlying model encoding)
    "openrouter/openai/gpt-4o-mini": "o200k_base",
    "openrouter/openai/gpt-4o": "o200k_base",
    # Ollama
    "ollama/gemma4:e2b": "cl100k_base",
    "ollama/llama3.2": "cl100k_base",
    # SiliconFlow / Together
    "siliconflow/deepseek-ai/DeepSeek-V3": "cl100k_base",
    "together/google/gemma-2-27b-it": "cl100k_base",
}

# Cache for encoding instances (avoids repeated get_encoding calls)
_encoding_cache: dict = {}


def _resolve_encoding(model: str = "") -> str:
    """Get tiktoken encoding name for a given model string."""
    if not model:
        return "cl100k_base"

    if model in MODEL_ENCODING_MAP:
        return MODEL_ENCODING_MAP[model]

    # Try to infer from litellm model info
    try:
        from litellm import get_model_info
        info = get_model_info(model)
        max_input = getattr(info, "max_input_tokens", None) or getattr(info, "max_tokens", None)
        if max_input:
            # Models with large context windows typically use o200k
            if max_input >= 128000:
                return "o200k_base"
            return "cl100k_base"
    except (ImportError, AttributeError, KeyError):
        pass

    # Default fallback
    return "cl100k_base"


def count_tokens(text: str, model: str = "") -> int:
    """Count tokens using tiktoken if available, else fallback to char/4.

    Args:
        text: The text to count tokens for.
        model: Optional model name for accurate encoding selection.

    Returns:
        Estimated token count.
    """
    if not text:
        return 0

    if HAS_TIKTOKEN and tiktoken is not None:
        try:
            encoding_name = _resolve_encoding(model)
            if encoding_name not in _encoding_cache:
                _encoding_cache[encoding_name] = tiktoken.get_encoding(encoding_name)
            encoding = _encoding_cache[encoding_name]
            return len(encoding.encode(text))
        except (KeyError, ValueError, TypeError):
            pass

    # Fallback: character / 4 (rough estimate)
    return len(text) // 4


def count_messages_tokens(messages: list[dict], model: str = "") -> int:
    """Count total tokens in a list of messages.

    Includes content, tool results, and tool call arguments.

    Args:
        messages: List of message dicts with 'content', 'result', 'tool_calls' keys.
        model: Optional model name for accurate encoding selection.

    Returns:
        Estimated total token count.
    """
    total = 0
    for m in messages:
        # Main content
        content = m.get("content", "") or ""
        total += count_tokens(str(content), model)

        # Tool result field (alternate naming)
        if "result" in m:
            total += count_tokens(str(m.get("result", "")), model)

        # Tool calls
        if "tool_calls" in m:
            for tc in m["tool_calls"]:
                if isinstance(tc, dict):
                    func = tc.get("function", {})
                    if isinstance(func, dict):
                        total += count_tokens(func.get("arguments", ""), model)
                elif hasattr(tc, "function"):
                    func = getattr(tc, "function", None)
                    if func is not None:
                        total += count_tokens(getattr(func, "arguments", ""), model)

    return total
