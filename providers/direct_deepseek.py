"""
Direct HTTP client for DeepSeek chat completions API.

Bypasses liteLLM overhead (~500ms–2s) by making raw HTTP calls
via httpx.AsyncClient with connection pooling.

Supports:
- Chat completions (streaming + non-streaming)
- Tool calling (send tool definitions, parse tool_calls)
- Exponential backoff retry (3 attempts)
- Prompt caching headers (X-DeepSeek-Cache: enable)
- Error mapping → FailoverReason taxonomy
"""
from __future__ import annotations

import json
import os
from typing import AsyncIterator, Optional

import httpx

from core.logger import log
from core.error_classifier import classify_api_error, FailoverReason

# ── Constants ────────────────────────────────────────────────

DEEPSEEK_API_BASE = "https://api.deepseek.com"
CHAT_ENDPOINT = f"{DEEPSEEK_API_BASE}/chat/completions"

# Retry config
MAX_RETRIES = 3
RETRY_DELAYS = [1.0, 3.0, 7.0]  # seconds

# Default timeout
TIMEOUT_SECONDS = 120

# Model name remap (litellm prefix → raw API name)
MODEL_NAME_MAP = {
    "deepseek/deepseek-chat": "deepseek-chat",
    "deepseek/deepseek-reasoner": "deepseek-reasoner",
}


def _map_model_name(model: str) -> str:
    """Strip litellm prefix for direct API calls."""
    return MODEL_NAME_MAP.get(model, model)


def _get_api_key() -> str:
    """Get DeepSeek API key from env or key manager."""
    key = os.getenv("DEEPSEEK_API_KEY", "")
    if key and key != "***":
        return key
    try:
        from providers.keys import keys as _km
        return _km.get_key("deepseek") or ""
    except (ImportError, AttributeError, KeyError):
        pass
    return os.getenv("API_KEY", "") or os.getenv("DORINA_API_KEY", "")


# ── Shared HTTP client (connection pooling) ─────────────────

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(TIMEOUT_SECONDS),
            limits=httpx.Limits(
                max_keepalive_connections=5,
                max_connections=10,
                keepalive_expiry=60.0,
            ),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
    return _client


# ── Error classification for httpx responses ────────────────


def _classify_httpx_error(error: Exception) -> str:
    """Map httpx errors to FailoverReason strings."""
    if isinstance(error, httpx.TimeoutException):
        return FailoverReason.TIMEOUT
    if isinstance(error, (httpx.ConnectError, httpx.RemoteProtocolError)):
        return FailoverReason.NETWORK
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        if status == 401 or status == 403:
            return FailoverReason.AUTH
        elif status == 429:
            return FailoverReason.RATE_LIMIT
        elif status == 503:
            return FailoverReason.OVERLOADED
        elif status >= 500:
            return FailoverReason.SERVER_ERROR
    return FailoverReason.UNKNOWN


# ── Main chat completion function ───────────────────────────


async def chat(
    model: str,
    messages: list[dict],
    tools: Optional[list[dict]] = None,
    max_tokens: int = 8192,
    temperature: float = 0.7,
    stream: bool = False,
    api_key: Optional[str] = None,
    stream_callback: Optional[callable] = None,
) -> dict:
    """Direct HTTP chat completion call to DeepSeek.

    Args:
        model: Model name (litellm format like "deepseek/deepseek-chat" or raw).
        messages: List of message dicts (system, user, assistant, tool).
        tools: Optional list of tool definitions.
        max_tokens: Max output tokens.
        temperature: Sampling temperature.
        stream: Whether to stream the response.
        api_key: API key (auto-resolved if not provided).
        stream_callback: Optional async callable called per content delta chunk.
                         Only used when stream=True.

    Returns:
        Dict with same shape as ReasoningEngine._parse_response():
            { "content": str, "tool_calls": list, "finish_reason": str,
              "usage": {"prompt_tokens": int, "completion_tokens": int},
              "cost": float }
    """
    key = api_key or _get_api_key()
    if not key:
        raise RuntimeError("DeepSeek API key not found — set DEEPSEEK_API_KEY")

    raw_model = _map_model_name(model)

    # Build request body
    body = {
        "model": raw_model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": stream,
    }

    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"

    last_error: Exception | None = None
    last_httpx_error: httpx.HTTPStatusError | None = None

    for attempt in range(MAX_RETRIES):
        client = _get_client()

        try:
            # Filter out unsupported params before sending
            if "tool_call_id" in body:
                body.pop("tool_call_id", None)

            headers = {
                "Authorization": f"Bearer {key}",
                "Accept": "application/json",
            }

            # Prompt caching header (DeepSeek supports X-DeepSeek-Cache)
            headers["X-DeepSeek-Cache"] = "enable"

            if stream:
                return await _chat_stream(client, body, headers, stream_callback=stream_callback)

            response = await client.post(
                CHAT_ENDPOINT,
                json=body,
                headers=headers,
            )

            if response.status_code == 200:
                return _parse_direct_response(response.json())

            # Error — classify and maybe retry
            try:
                err_data = response.json()
                err_msg = err_data.get("error", {}).get("message", str(response.text))
            except (json.JSONDecodeError, AttributeError):
                err_msg = response.text[:500]

            status = response.status_code
            httpx_error = httpx.HTTPStatusError(err_msg, request=response.request, response=response)
            reason = _classify_httpx_error(httpx_error)
            last_httpx_error = httpx_error

            log.warning(
                f"DeepSeek direct HTTP error (attempt {attempt + 1}/{MAX_RETRIES}): "
                f"status={status} reason={reason} msg={err_msg[:100]}"
            )

            # Non-retryable errors: auth, billing, content policy
            if reason in (FailoverReason.AUTH, FailoverReason.AUTH_PERMANENT):
                raise RuntimeError(
                    f"DeepSeek API auth error (HTTP {status}): {err_msg[:200]}"
                )

            # Retryable: rate limit, overloaded, server error, timeout
            if attempt < MAX_RETRIES - 1 and reason in (
                FailoverReason.RATE_LIMIT,
                FailoverReason.OVERLOADED,
                FailoverReason.SERVER_ERROR,
                FailoverReason.TIMEOUT,
                FailoverReason.NETWORK,
            ):
                delay = RETRY_DELAYS[attempt]
                log.info(f"Retrying in {delay}s (attempt {attempt + 2}/{MAX_RETRIES})...")
                import asyncio
                await asyncio.sleep(delay)
                continue

            # All retries exhausted for HTTP error — re-raise httpx exception
            # so the error classifier in _handle_llm_error can extract status codes
            raise httpx_error

        except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError) as e:
            last_error = e
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAYS[attempt]
                log.info(f"DeepSeek connection error ({type(e).__name__}), retrying in {delay}s...")
                import asyncio
                await asyncio.sleep(delay)
                continue
            # All retries exhausted — re-raise original httpx exception
            raise

    # All retries exhausted — raise last httpx error if available, otherwise a generic error
    if last_httpx_error:
        raise last_httpx_error
    raise RuntimeError(
        f"DeepSeek API failed after {MAX_RETRIES} attempts: "
        f"{last_error or 'unknown error'}"
    )


# ── Streaming ───────────────────────────────────────────────


async def _chat_stream(
    client: httpx.AsyncClient,
    body: dict,
    headers: dict,
    stream_callback: Optional[callable] = None,
) -> dict:
    """Streaming chat completion — accumulate chunks, return parsed result."""
    body["stream"] = True

    content_chunks: list[str] = []
    tool_call_deltas: dict[int, dict] = {}
    finish_reason = "stop"

    async with client.stream(
        "POST",
        CHAT_ENDPOINT,
        json=body,
        headers=headers,
    ) as response:
        if response.status_code != 200:
            err_body = await response.aread()
            raise httpx.HTTPStatusError(
                f"DeepSeek streaming error (HTTP {response.status_code})",
                request=response.request,
                response=response,
            )

        async for line in response.aiter_lines():
            line = line.strip()
            if not line or line.startswith(":"):
                continue  # SSE comment / keepalive
            if line == "data: [DONE]":
                break
            if not line.startswith("data: "):
                continue

            try:
                chunk = json.loads(line[6:])
            except json.JSONDecodeError:
                continue

            if "choices" not in chunk or not chunk["choices"]:
                continue

            delta = chunk["choices"][0].get("delta", {})
            if not delta:
                continue

            if delta.get("content"):
                content_chunks.append(delta["content"])
                if stream_callback:
                    stream_callback(delta["content"])

            if delta.get("tool_calls"):
                for tc in delta["tool_calls"]:
                    idx = tc.get("index", 0)
                    if idx not in tool_call_deltas:
                        tool_call_deltas[idx] = {
                            "id": tc.get("id", ""),
                            "type": "function",
                            "function": {"name": "", "arguments": ""},
                        }
                    fn = tc.get("function", {})
                    if fn.get("name"):
                        tool_call_deltas[idx]["function"]["name"] += fn["name"]
                    if fn.get("arguments"):
                        tool_call_deltas[idx]["function"]["arguments"] += fn["arguments"]

            if chunk["choices"][0].get("finish_reason"):
                finish_reason = chunk["choices"][0]["finish_reason"]

    content = "".join(content_chunks)

    # Estimate token usage (rough approximation)
    _est_in = _estimate_prompt_tokens(body.get("messages", []))
    _est_out = len(content.split()) * 1.3 if content else 0

    result = {
        "content": content,
        "tool_calls": [],
        "finish_reason": finish_reason,
        "usage": {
            "prompt_tokens": int(_est_in),
            "completion_tokens": int(max(_est_out, 1)),
        },
        "cost": 0,
    }

    if tool_call_deltas:
        result["tool_calls"] = [
            tool_call_deltas[i] for i in sorted(tool_call_deltas.keys())
        ]

    return result


# ── Response parsing ────────────────────────────────────────


def _parse_direct_response(data: dict) -> dict:
    """Parse DeepSeek REST API response into common dict format.

    The returned dict matches the shape of ReasoningEngine._parse_response()
    so it can be used interchangeably.
    """
    if "choices" not in data or not data["choices"]:
        return {
            "content": "",
            "tool_calls": [],
            "finish_reason": "no_choices",
            "usage": {"prompt_tokens": 0, "completion_tokens": 0},
            "cost": 0,
        }

    choice = data["choices"][0]
    msg = choice.get("message", {})
    usage = data.get("usage", {})

    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)

    result = {
        "content": msg.get("content", "") or "",
        "tool_calls": [],
        "finish_reason": choice.get("finish_reason", "stop"),
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        },
        "cost": _estimate_cost(prompt_tokens, completion_tokens),
    }

    if msg.get("tool_calls"):
        result["tool_calls"] = [
            {
                "id": tc["id"],
                "type": "function",
                "function": {
                    "name": tc["function"]["name"],
                    "arguments": tc["function"]["arguments"],
                },
            }
            for tc in msg["tool_calls"]
        ]

    return result


# ── Cost estimation ─────────────────────────────────────────


def _estimate_cost(prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate cost in USD for DeepSeek API call.

    DeepSeek pricing (as of 2026):
    - deepseek-chat: $0.14/M input, $0.28/M output
    - deepseek-reasoner: $0.55/M input, $2.19/M output (not handled separately)
    """
    input_rate = 0.14 / 1_000_000
    output_rate = 0.28 / 1_000_000
    return prompt_tokens * input_rate + completion_tokens * output_rate


def _estimate_prompt_tokens(messages: list[dict]) -> int:
    """Rough token estimate for messages."""
    from core.tokenizer import count_messages_tokens
    try:
        return count_messages_tokens(messages)
    except (ImportError, AttributeError):
        total = 0
        for m in messages:
            content = str(m.get("content", ""))
            total += len(content) // 2  # rough: ~2 chars per token
        return total


# ── Utility: check connectivity ─────────────────────────────


async def check_connectivity() -> bool:
    """Ping DeepSeek API to verify key and connectivity."""
    key = _get_api_key()
    if not key:
        return False
    try:
        client = _get_client()
        resp = await client.get(
            f"{DEEPSEEK_API_BASE}/models",
            headers={"Authorization": f"Bearer {key}"},
        )
        return resp.status_code == 200
    except (httpx.HTTPError, OSError):
        return False


# ── Reset client (for testing/cleanup) ──────────────────────


def reset_client():
    """Reset the shared HTTP client (e.g., on session end)."""
    global _client
    if _client is not None:
        import asyncio
        try:
            asyncio.create_task(_client.aclose())
        except RuntimeError:
            pass  # no running loop
        _client = None
