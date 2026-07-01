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

    @property
    def model(self):
        return settings.model.default

    @property
    def provider(self):
        return settings.model.provider

    def get_model_string(self) -> str:
        """litellm formatında model string'i döndür (örn: gemini/gemini-2.5-flash)."""
        active_model = self.model
        active_provider = self.provider
        if active_provider in ("google", "gemini"):
            if not active_model.startswith("gemini/"):
                raw = active_model.split("/", 1)[-1] if "/" in active_model else active_model
                return f"gemini/{raw}"
        if "/" not in active_model and active_provider:
            return f"{active_provider}/{active_model}"
        return active_model

    _shared_llm = None

    # ─── Cross-provider model fallback chain ───
    # (provider, litellm_model_name) tuples — tried in order when primary fails
    MODEL_FALLBACK_CHAIN: list[tuple[str, str]] = [
        # (provider, litellm_model_name) — tried in order when primary fails
        ("deepseek", "deepseek/deepseek-chat"),
        ("deepseek", "deepseek/deepseek-reasoner"),
    ]

    def _get_fallback_chain(self, exclude_provider: str = "", exclude_model: str = "") -> list[tuple[str, str]]:
        """Return fallback chain, optionally excluding a specific (provider, model) pair.
        
        This method is independent of current provider setting — always returns the
        same chain regardless of what provider is configured.
        The first entry is always the primary model from settings.
        """
        # Start with all available fallbacks
        chain = list(self.__class__.MODEL_FALLBACK_CHAIN)

        # Remove the failed model if it appears in the list
        if exclude_model:
            chain = [(p, m) for p, m in chain if not (p == exclude_provider and m == exclude_model)]

        return chain

    def _get_llm(self):
        if ReasoningEngine._shared_llm is None:
            try:
                import os as _os
                _os.environ.setdefault("LITELLM_LOG", "WARNING")
                _os.environ.setdefault("OPENAI_LOG_LEVEL", "WARNING")
                _os.environ.setdefault("LITELLM_SUPPRESS_DEBUG_INFO", "1")
                _os.environ.setdefault("LITELLM_VERBOSE", "False")
                _os.environ.setdefault("LITELLM_DEBUG", "False")
                _os.environ.setdefault("ANTHROPIC_LOG_LEVEL", "ERROR")
                _os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

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
        provider = self.provider
        if provider not in CACHE_ENABLED_PROVIDERS:
            return {}

        current_hash = str(hash(system_prompt))
        system_prompt_changed = (
            ReasoningEngine._last_system_prompt_hash is not None
            and ReasoningEngine._last_system_prompt_hash != current_hash
        )
        ReasoningEngine._last_system_prompt_hash = current_hash

        if CACHE_STRATEGY == "conservative" and system_prompt_changed:
            log.debug(f"System prompt changed — skipping cache")
            return {}

        if provider == "deepseek":
            return {
                "cache": {
                    "no-cache": False,
                    "ttl": CACHE_TTL,
                    "max_size": MAX_CACHE_SIZE,
                }
            }
        elif provider == "anthropic":
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
        """LLM'e sor, yanıt al. (async) + prompt caching + opsiyonel streaming."""
        llm = self._get_llm()

        full_messages = [{"role": "system", "content": system_prompt}]
        full_messages.extend(messages)

        api_key = self._get_api_key()

        model_name = self.model
        # litellm uses "gemini/" prefix for Google models, not "google/"
        if self.provider in ("google", "gemini"):
            if not model_name.startswith("gemini/"):
                # Strip any "google/" prefix, add "gemini/"
                raw = model_name.split("/", 1)[-1] if "/" in model_name else model_name
                model_name = f"gemini/{raw}"
        elif self.provider == "openrouter" and not model_name.startswith("openrouter/"):
            model_name = f"openrouter/{model_name}"
        elif "/" not in model_name and self.provider:
            model_name = f"{self.provider}/{model_name}"

        params = {
            "model": model_name,
            "messages": full_messages,
            "api_key": api_key,
            "max_tokens": settings.model.max_tokens, # Config'den alınır
        }

        # Safety Settings for Gemini (if provider is google/gemini)
        if self.provider in ("google", "gemini"):
            params["safety_settings"] = [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_CIVIC_INTEGRITY", "threshold": "BLOCK_NONE"},
            ]
            # Litellm'de max_tokens ayrı parametre olarak verilir, generationConfig yerine
            params["max_tokens"] = 65535 # Gemini'ye özel yüksek token limiti

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
            return await self._handle_llm_error(e, llm, params, model_name, full_messages, stream_callback)

    async def _handle_llm_error(
        self, e: Exception, llm, params: dict, model_name: str,
        full_messages: list, stream_callback=None
    ) -> dict:
        """Cross-provider fallback: try model chain on retryable errors."""
        from core.error_classifier import classify_api_error, FailoverReason
        classified = classify_api_error(e, provider=self.provider, model=model_name)

        if classified.reason in [FailoverReason.RATE_LIMIT, FailoverReason.OVERLOADED,
                                  FailoverReason.SERVER_ERROR, FailoverReason.TIMEOUT,
                                  FailoverReason.MODEL_NOT_FOUND]:
            import asyncio
            from ui import display as _display
            from providers.keys import keys as _km, ENV_MAP

            # Build fallback chain, excluding the model that just failed
            fallback_chain = self._get_fallback_chain(exclude_provider=self.provider, exclude_model=model_name)

            for attempt, (fb_provider, fb_model_name) in enumerate(fallback_chain, 1):
                retry_wait = 5 * attempt  # 5sn, 10sn, 15sn...
                log.warning(f"Fallback {attempt}: {model_name} → {fb_model_name} ({fb_provider})")
                _display.print_info(f"Model {model_name} hata verdi. {retry_wait}s sonra {fb_model_name} deneniyor... ☕")
                await asyncio.sleep(retry_wait)

                # Build new params for this model/provider
                fb_params = params.copy()
                fb_params["model"] = fb_model_name
                fb_params["api_key"] = _km.get_key(fb_provider) or os.getenv(ENV_MAP.get(fb_provider, ""), "")

                # Safety settings for Gemini
                if fb_provider in ("google", "gemini"):
                    fb_params["safety_settings"] = [
                        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                        {"category": "HARM_CATEGORY_CIVIC_INTEGRITY", "threshold": "BLOCK_NONE"},
                    ]
                    fb_params["max_tokens"] = 65535
                else:
                    fb_params.pop("safety_settings", None)
                    fb_params["max_tokens"] = settings.model.max_tokens

                try:
                    log.info(f"Deniyorum: {fb_model_name}")
                    if stream_callback:
                        return await self._think_stream(llm, fb_params, stream_callback)
                    resp = await llm.acompletion(**fb_params)
                    return self._parse_response(resp)
                except Exception as fb_e:
                    log.error(f"Fallback basarisiz ({fb_model_name}): {fb_e}")
                    e = fb_e  # son hatayı tut

        # All fallbacks exhausted — clean user message and raise
        log.error(f"LLM ERROR [{classified.reason}]: {type(e).__name__}: {str(e)[:200]}")
        log.error(f"  model={model_name}, provider={self.provider}")
        log.error(f"  recovery: compress={classified.should_compress} rotate={classified.should_rotate_credential} fallback={classified.should_fallback}")
        try:
            from core.error_db import log_llm_error
            log_llm_error(provider=self.provider, model=model_name, error=e)
        except Exception:
            pass
        last_msgs = full_messages[-5:] if len(full_messages) >= 5 else full_messages
        for i, m in enumerate(last_msgs):
            r = m.get("role", "")
            c = (m.get("content") or "")[:80]
            tc = m.get("tool_calls")
            tci = m.get("tool_call_id", "")
            log.error(f"  msg[-{len(last_msgs)-i}]: role={r} content={c} tc={bool(tc)} tcid={tci}")
        raise

    async def _think_stream(self, llm, params: dict, callback: callable) -> dict:
        """Streaming LLM call — accumulate chunks, yield via callback."""
        content_chunks: list[str] = []
        tool_call_deltas: dict[int, dict] = {}
        finish_reason = "stop"

        stream = await llm.acompletion(stream=True, **params)

        async for chunk in stream:
            if not chunk.choices:
                log.warning(f"LLM stream chunk has no choices for model {params.get('model')}")
                continue

            delta = chunk.choices[0].delta if chunk.choices else None
            if not delta:
                continue

            if delta.content:
                content_chunks.append(delta.content)
                callback(delta.content)

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

            if chunk.choices[0].finish_reason:
                finish_reason = chunk.choices[0].finish_reason

        content = "".join(content_chunks)
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

        # ── Token budget kontrolü (stream) ──
        from core.mode_manager import modes
        _est_total = _est_in + _est_out
        if _est_total > 0 and modes.budget_hit(_est_total):
            from ui.display import print_warning
            print_warning(f"Token budget asildi! ({modes.budget_used}/{modes.budget})")
            result["_budget_breached"] = True

        return result

    def _parse_response(self, response) -> dict:
        """LLM yanıtını parse et + token budget kontrolü."""
        if not response.choices:
            log.warning(f"LLM response has no choices for model {response.model}")
            return {"content": "", "tool_calls": [], "finish_reason": "no_choices", "usage": {"prompt_tokens": 0, "completion_tokens": 0}, "cost": 0}

        choice = response.choices[0]
        prompt_tokens = response.usage.prompt_tokens if response.usage else 0
        completion_tokens = response.usage.completion_tokens if response.usage else 0
        total_tokens = prompt_tokens + completion_tokens

        result = {
            "content": choice.message.content or "",
            "tool_calls": [],
            "finish_reason": getattr(choice, "finish_reason", "stop"),
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
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

        # ── Token budget kontrolü ──
        from core.mode_manager import modes
        if total_tokens > 0 and modes.budget_hit(total_tokens):
            from ui.display import print_warning
            print_warning(f"Token budget asildi! ({modes.budget_used}/{modes.budget})")
            result["_budget_breached"] = True

        return result

    def _get_api_key(self) -> str | None:
        key_map = {
            "openrouter": "OPENROUTER_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "groq": "GROQ_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "google": "GOOGLE_API_KEY",
            "gemini": "GOOGLE_API_KEY",
            "siliconflow": "SILICONFLOW_API_KEY",
            "together": "TOGETHER_API_KEY",
        }
        try:
            from providers.keys import keys as _km
            mgr_key = _km.get_key(self.provider)
            if mgr_key:
                return mgr_key
        except Exception:
            pass

        env_key = key_map.get(self.provider)
        if env_key:
            key = os.getenv(env_key)
            if key and key != "***":
                return key

        return os.getenv("API_KEY") or os.getenv("DORINA_API_KEY")

    def reset_cache(self):
        ReasoningEngine._last_system_prompt_hash = None
