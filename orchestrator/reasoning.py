"""LLM reasoning - litellm ile model çağrıları + prompt caching (async)."""

from __future__ import annotations
import json
import os
import asyncio
from typing import Optional

from core.logger import log
from core.config import settings
from core.constants import (
    CACHE_TTL,
    MAX_CACHE_SIZE,
    CACHE_ENABLED_PROVIDERS,
    CACHE_STRATEGY,
)


class ReasoningEngine:
    """LLM communication via litellm + prompt caching support (async)."""

    # Track system prompt hash to detect changes (cache invalidation)
    _last_system_prompt_hash: str | None = None

    def __init__(self):
        self.llm = None
        # Initialize provider router
        from providers.router import router
        self._router = router

    @property
    def model(self):
        """Live-read model from config (not cached)."""
        return settings.model.default

    @property
    def provider(self):
        """Live-read provider from config (not cached)."""
        return settings.model.provider

    @property
    def fallbacks(self):
        """Live-read fallback providers from config."""
        return settings.model.fallback_providers

    _shared_llm = None

    def _get_llm(self):
        if ReasoningEngine._shared_llm is None:
            try:
                # Environment-level suppression (catch-all for litellm internal logs)
                import os as _os
                _os.environ.setdefault("LITELLM_LOG", "WARNING")
                _os.environ.setdefault("OPENAI_LOG_LEVEL", "WARNING")
                _os.environ.setdefault("LITELLM_SUPPRESS_DEBUG_INFO", "1")
                _os.environ.setdefault("LITELLM_VERBOSE", "False")
                _os.environ.setdefault("LITELLM_DEBUG", "False")
                _os.environ.setdefault("ANTHROPIC_LOG_LEVEL", "ERROR")
                _os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")  # Suppress boto3 region warnings

                import litellm
                litellm.drop_params = True
                litellm.suppress_debug_info = True
                litellm.set_verbose = False
                litellm.turn_off_message_logging = True
                litellm.telemetry = False
                litellm.disable_streaming_logging = True
                litellm.store_audit_logs = False
                litellm.disable_end_user_cost_tracking = True
                litellm.global_disable_no_log_param = True
                ReasoningEngine._shared_llm = litellm
            except ImportError:
                log.error("litellm yüklenemedi! pip install litellm")
                raise
        return ReasoningEngine._shared_llm

    def _get_cache_params(self, system_prompt: str) -> dict:
        """Cache parametrelerini provider'a göre ayarla.

        DeepSeek: caching via model params (cache_key, ttl)
        Anthropic: native prompt caching via cache_control
        Other providers: no caching
        """
        provider = self.provider
        if provider not in CACHE_ENABLED_PROVIDERS:
            return {}

        # System prompt değişti mi? (cache invalidation)
        current_hash = str(hash(system_prompt))
        system_prompt_changed = (
            ReasoningEngine._last_system_prompt_hash is not None
            and ReasoningEngine._last_system_prompt_hash != current_hash
        )
        ReasoningEngine._last_system_prompt_hash = current_hash

        # Conservative strategy: only cache if system prompt hasn't changed
        if CACHE_STRATEGY == "conservative" and system_prompt_changed:
            log.debug(f"System prompt changed — skipping cache")
            return {}

        # Provider-specific caching
        if provider == "deepseek":
            # DeepSeek supports caching via litellm's caching params
            return {
                "cache": {
                    "no-cache": False,
                    "ttl": CACHE_TTL,
                    "max_size": MAX_CACHE_SIZE,
                }
            }
        elif provider == "anthropic":
            # Anthropic prompt caching — mark system message for caching
            return {
                "caching": True,
                "cache_control": {"type": "ephemeral"},
                "ttl": CACHE_TTL,
            }

        return {}

    async def think(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        stream_callback: Optional[callable] = None,
    ) -> dict:
        """LLM'e sor, yanıt al. (async) + prompt caching + opsiyonel streaming.

        stream_callback: Her token chunk'ı için çağrılır (streaming mod).
                        Sağlanırsa stream=True ile çağrı yapılır.
        """
        llm = self._get_llm()

        full_messages = [{"role": "system", "content": system_prompt}]
        full_messages.extend(messages)

        # Load API key (from key manager first, then env)
        api_key = self._get_api_key()

        # Fix model name: add provider prefix if needed
        model_name = self.model
        if self.provider == "openrouter" and not model_name.startswith("openrouter/"):
            model_name = f"openrouter/{model_name}"
        elif "/" not in model_name and self.provider:
            model_name = f"{self.provider}/{model_name}"

        params = {
            "model": model_name,
            "messages": full_messages,
            "api_key": api_key,
        }

        # ── P0-06: Prompt caching ──────────────────────────────────
        cache_params = self._get_cache_params(system_prompt)
        if cache_params:
            params.update(cache_params)
            log.debug(f"Prompt caching enabled: provider={self.provider}, strategy={CACHE_STRATEGY}")

        if tools:
            params["tools"] = tools
            params["tool_choice"] = "auto"

        try:
            log.debug(f"LLM call: model={model_name}, provider={self.provider}")

            if stream_callback:
                return await self._think_stream(llm, params, stream_callback)

            response = await llm.acompletion(**params)
            return self._parse_response(response)
        except Exception as e:
            from core.error_classifier import classify_api_error
            classified = classify_api_error(e, provider=self.provider, model=model_name)
            
            # Auto-Retry for Rate Limits and Timeouts
            if classified.reason in ["RateLimitError", "APIConnectionError", "Timeout"]:
                import asyncio
                from ui import display as _display
                retry_wait = 10
                log.warning(f"API {classified.reason} alindi! {retry_wait} saniye dinleniliyor, sonra tekrar denenecek...")
                _display.print_info(f"Yogunluk/Limit Hatasi: Sistem {retry_wait} saniye soluklanip tekrar deneyecek (Mola) ☕")
                await asyncio.sleep(retry_wait)
                try:
                    log.info(f"Mola bitti, {self.provider} uzerinden tekrar deneniyor...")
                    if stream_callback:
                        return await self._think_stream(llm, params, stream_callback)
                    response = await llm.acompletion(**params)
                    return self._parse_response(response)
                except Exception as retry_e:
                    log.error(f"Tekrar deneme basarisiz: {retry_e}")
                    e = retry_e # Fallback'e dusmesi icin asil hatayi guncelle
            
            log.error(f"LLM ERROR [{classified.reason}]: {type(e).__name__}: {str(e)[:200]}")
            log.error(f"  model={model_name}, provider={self.provider}, key_len={len(api_key) if api_key else 0}")
            log.error(f"  recovery: compress={classified.should_compress} rotate={classified.should_rotate_credential} fallback={classified.should_fallback}")
            # Log to error database
            try:
                from core.error_db import log_llm_error
                log_llm_error(
                    message=str(e)[:500],
                    category=classified.reason,
                    provider=self.provider,
                    model=model_name,
                )
            except Exception:
                pass
            # Log last 5 messages for debugging
            last_msgs = full_messages[-5:] if len(full_messages) >= 5 else full_messages
            for i, m in enumerate(last_msgs):
                r = m.get("role", "")
                c = (m.get("content") or "")[:80]
                tc = m.get("tool_calls")
                tci = m.get("tool_call_id", "")
                log.error(f"  msg[-{len(last_msgs)-i}]: role={r} content={c} tc={bool(tc)} tcid={tci}")
            if self.fallbacks and classified.reason not in ("BadRequestError", "AuthenticationError", "PermissionDeniedError"):
                return await self._try_fallback(system_prompt, messages, tools)
            raise

    async def _think_stream(self, llm, params: dict, callback: callable) -> dict:
        """Streaming LLM call — accumulate chunks, yield via callback.

        Returns the same dict format as _parse_response().
        """
        content_chunks: list[str] = []
        tool_call_deltas: dict[int, dict] = {}
        finish_reason = "stop"

        stream = await llm.acompletion(stream=True, **params)

        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if not delta:
                continue

            # Content chunk
            if delta.content:
                content_chunks.append(delta.content)
                callback(delta.content)

            # Tool call chunks — accumulate deltas
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_call_deltas:
                        tool_call_deltas[idx] = {
                            "id": tc.id or "",
                            "type": "function",
                            "function": {"name": "", "arguments": ""},
                        }
                    if tc.function:
                        if tc.function.name:
                            tool_call_deltas[idx]["function"]["name"] += tc.function.name
                        if tc.function.arguments:
                            tool_call_deltas[idx]["function"]["arguments"] += tc.function.arguments

            # Finish reason
            if chunk.choices[0].finish_reason:
                finish_reason = chunk.choices[0].finish_reason

        # Build response in same format as _parse_response
        content = "".join(content_chunks)
        # Estimate tokens from content length (rough: 4 chars ≈ 1 token)
        _est_prompt = params.get("messages", [])
        _prompt_chars = sum(len(str(m.get("content", ""))) for m in _est_prompt)
        _est_in = _prompt_chars // 4
        _est_out = len(content) // 4
        if content:
            _est_out = max(_est_out, 1)
        result = {
            "content": content,
            "tool_calls": [],
            "finish_reason": finish_reason,
            "usage": {"prompt_tokens": _est_in, "completion_tokens": _est_out},
            "cost": 0,
            "_streamed": True,
        }

        if tool_call_deltas:
            result["tool_calls"] = [
                tool_call_deltas[i] for i in sorted(tool_call_deltas.keys())
            ]

        return result

    async def _try_fallback(
        self, system_prompt: str, messages: list[dict], tools: Optional[list[dict]]
    ) -> dict:
        """Provider router üzerinden async fallback dene."""
        llm = self._get_llm()
        full_messages = [{"role": "system", "content": system_prompt}]
        full_messages.extend(messages)

        # API key env mapping for fallback providers
        KEY_ENV_MAP = {
            "openrouter": "OPENROUTER_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "groq": "GROQ_API_KEY",
            "openai": "OPENAI_API_KEY",
            "siliconflow": "SILICONFLOW_API_KEY",
            "together": "TOGETHER_API_KEY",
            "google": "GOOGLE_API_KEY",
        }

        # Reset router state before starting fallback cycle
        self._router.reset()

        while True:
            provider = await self._router.fallback()
            if not provider:
                break
            try:
                log.info(f"Fallback deneniyor: {provider['name']} ({provider['model']})")

                # Look up API key for this fallback provider
                pname = provider["name"]
                fb_key = ""
                try:
                    from providers.keys import keys as _km
                    fb_key = _km.get_key(pname)
                except ImportError:
                    pass
                if not fb_key:
                    env_var = KEY_ENV_MAP.get(pname)
                    if env_var:
                        fb_key = os.getenv(env_var, "")

                params = {
                    "model": provider["model"],
                    "messages": full_messages,
                    "api_key": fb_key or None,
                }
                if tools:
                    params["tools"] = tools
                    params["tool_choice"] = "auto"

                response = await llm.acompletion(**params)
                log.info(f"Fallback basarili: {provider['name']}")
                return self._parse_response(response)
            except Exception as e:
                log.warning(f"Fallback [{provider['name']}] basarisiz: {e}")
                continue

        raise Exception("Tum provider'lar basarisiz oldu")

    def _parse_response(self, response) -> dict:
        """LLM yanıtını parse et."""
        choice = response.choices[0]
        result = {
            "content": choice.message.content or "",
            "tool_calls": [],
            "finish_reason": getattr(choice, "finish_reason", "stop"),
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            },
            "cost": getattr(response, "_cost", 0),
        }

        if choice.message.tool_calls:
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in choice.message.tool_calls
            ]

        return result

    def _get_api_key(self) -> str | None:
        key_map = {
            "openrouter": "OPENROUTER_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "groq": "GROQ_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "google": "GOOGLE_API_KEY",
            "siliconflow": "SILICONFLOW_API_KEY",
            "together": "TOGETHER_API_KEY",
        }
        # Always use key manager (env vars may be masked)
        try:
            from providers.keys import keys as _km
            mgr_key = _km.get_key(self.provider)
            if mgr_key:
                return mgr_key
        except Exception:
            pass

        # Fallback: check env vars as last resort
        env_key = key_map.get(self.provider)
        if env_key:
            key = os.getenv(env_key)
            if key and key != "***":
                return key

        return os.getenv("API_KEY") or os.getenv("DORINA_API_KEY")

    def reset_cache(self):
        """Cache state'ini sıfırla (system prompt değişikliği durumunda)."""
        ReasoningEngine._last_system_prompt_hash = None
        log.info("Prompt cache state reset")
