"""Provider routing — model yedekleme + fallback zinciri.

DeepSeek çökerse → Groq'a, o da çökerse → Ollama'ya geçer.
Her fallback adımı error_classifier + error_db ile loglanır.
"""
from __future__ import annotations
import os
from typing import Optional

from core.logger import log


class ProviderRouter:
    """LLM sağlayıcı yönlendirici. Otomatik fallback."""

    def __init__(self):
        self.providers: list[dict] = []
        self._current = 0
        self.fallback_chain: list[str] = []  # Track fallback history

    def add_provider(self, name: str, model: str, api_key: str = "", weight: int = 1):
        """Sağlayıcı ekle. weight=öncelik."""
        self.providers.append({
            "name": name,
            "model": model,
            "api_key": api_key or os.environ.get(f"{name.upper()}_API_KEY", ""),
            "weight": weight,
        })
        self.providers.sort(key=lambda p: p["weight"])  # Düşük weight = önce dene

    def get_current(self) -> dict:
        """Şu anki sağlayıcı."""
        return self.providers[self._current] if self.providers else {}

    def fallback(self, error: Optional[Exception] = None) -> Optional[dict]:
        """Sonraki sağlayıcıya geç. Once 5sn bekle, sonra gec."""
        import time
        time.sleep(5)

        prev = self.providers[self._current] if self._current < len(self.providers) else None

        self._current += 1
        if self._current < len(self.providers):
            next_p = self.providers[self._current]
            prev_name = prev["name"] if prev else "?"
            prev_model = prev["model"] if prev else "?"

            # Classify error if provided
            error_category = "unknown"
            if error is not None:
                try:
                    from core.error_classifier import classify_api_error
                    classified = classify_api_error(
                        error,
                        provider=prev_name,
                        model=prev_model,
                    )
                    error_category = classified.reason
                    log.warning(
                        f"Fallback [{prev_name}/{prev_model}] "
                        f"hata_kategorisi={error_category} "
                        f"status={classified.status_code} "
                        f"→ {next_p['name']}/{next_p['model']}"
                    )
                except Exception:
                    log.warning(
                        f"Fallback [{prev_name}/{prev_model}] "
                        f"→ {next_p['name']}/{next_p['model']}"
                    )
            else:
                log.warning(
                    f"Fallback [{prev_name}/{prev_model}] "
                    f"→ {next_p['name']}/{next_p['model']}"
                )

            # Log to error database
            try:
                from core.error_db import log_llm_error
                log_llm_error(
                    message=f"Fallback: {prev_name}/{prev_model} → {next_p['name']}/{next_p['model']}",
                    category=error_category,
                    provider=prev_name,
                    model=prev_model,
                )
            except Exception:
                pass

            # Track chain
            self.fallback_chain.append(
                f"{prev_name} {error_category} ({prev_model})"
            )

            return next_p

        # All providers exhausted - log it
        self._current = 0
        log.error("Tum provider'lar denendi, hicbiri basarili olmadi")
        try:
            from core.error_db import log_system_error
            chain_str = " → ".join(self.fallback_chain) if self.fallback_chain else "none"
            log_system_error(
                message=f"Tum provider'lar basarisiz. Zincir: {chain_str}",
            )
        except Exception:
            pass
        return None

    def reset(self):
        """Başa dön."""
        self._current = 0
        self.fallback_chain = []

    def get_fallback_summary(self) -> str:
        """Fallback zincirini özet olarak döndür.

        Örnek: "DeepSeek rate_limit → Groq auth → OpenRouter çalıştı"
        """
        if not self.fallback_chain:
            return ""
        return " → ".join(self.fallback_chain)

    def list(self) -> list[dict]:
        """Tüm sağlayıcıları listele."""
        return [
            {"name": p["name"], "model": p["model"], "active": i == self._current}
            for i, p in enumerate(self.providers)
        ]

    def select_provider(self, messages: list, tool_count: int = 0) -> str:
        """Maliyet-aware routing: basit görev → fast model, karmaşık → default.

        Args:
            messages: Mesaj listesi (token sayısı için)
            tool_count: Bu turdaki tool çağrısı adedi

        Returns:
            Seçilen model adı
        """
        # Rough token estimation
        total_chars = sum(len(str(m.get("content", ""))) for m in messages)
        estimated_tokens = total_chars // 4

        # Simple task: < 500 tokens AND < 3 tools
        if estimated_tokens < 500 and tool_count < 3:
            # Try to find a fast model in configured providers
            from core.config import settings as _st
            fast = getattr(getattr(_st, 'model', None), 'fast_model', None)
            if fast:
                log.debug(f"Router: fast model selected ({fast}) for simple task")
                return fast

        # Default model
        from core.config import settings as _st
        default = getattr(getattr(_st, 'model', None), 'default', 'deepseek/deepseek-v4-flash')
        log.debug(f"Router: default model selected ({default}) for complex task")
        return default


router = ProviderRouter()

# Dinamik provider yuklemesi: API key'i olan provider'lari otomatik ekle
from providers.keys import keys as _key_mgr, PROVIDERS as _all_providers
_available = _key_mgr.list_available()
_weight = 1
for _p in _available:
    _name = _p['name']
    _info = _all_providers.get(_name, {})
    _models = _info.get('models', [])
    if _models:
        router.add_provider(_name, f"{_name}/{_models[0]}", weight=_weight)
        _weight += 1
    # Ollama her zaman ekle (API key gerektirmez)
    if _name == 'ollama':
        router.add_provider("ollama", "ollama/llama3", weight=99)
if _weight == 1:
    # Hicbir API key bulunamadiysa varsayilan
    router.add_provider("deepseek", "deepseek/deepseek-v4-flash", weight=1)
    router.add_provider("groq", "groq/llama-3.3-70b-versatile", weight=2)
