"""Gelişmiş metrik toplama — token tüketimi, maliyet tracking, tool kullanım pattern'leri.

Session cost tracking:
  - Her LLM çağrısının maliyeti otomatik hesaplanır
  - total_cost_per_session tüm session maliyetini tutar
  - format_cost() okunabilir string döndürür
  - Model fiyatlandırması config/model.pricing'den okunur
  - Tool kullanım pattern'leri (hangi tool kaç kere çağrılmış)
"""

from __future__ import annotations
import time
import json
from typing import Optional
from collections import defaultdict
from dataclasses import dataclass, field
from core.config import settings


def get_model_pricing(model_name: str | None = None) -> dict:
    """Belirtilen modelin token fiyatlandırmasını döndür.

    Returns: {"input": float, "output": float, "cached_input": float}
    """
    pricing = settings.model.pricing
    if not pricing:
        return {"input": 0.00015, "output": 0.0006, "cached_input": 0.000075}
    model = model_name or settings.model.active_model or settings.model.default
    if model in pricing:
        return pricing[model]
    # If model doesn't match exactly, try prefix matching
    for key in pricing:
        if model.startswith(key):
            return pricing[key]
    return pricing.get("default", {"input": 0.00015, "output": 0.0006, "cached_input": 0.000075})


def calculate_tool_cost(
    input_tokens: int = 0,
    output_tokens: int = 0,
    cached_input_tokens: int = 0,
    model: str | None = None,
) -> float:
    """Bir LLM çağrısının maliyetini USD cinsinden hesapla."""
    pricing = get_model_pricing(model)
    cost = (
        (input_tokens - cached_input_tokens) * pricing["input"]
        + cached_input_tokens * pricing.get("cached_input", pricing["input"] / 2)
        + output_tokens * pricing["output"]
    ) / 1000  # pricing 1K token başına
    return max(cost, 0.0)


def format_cost(cost: float, currency: str = "$") -> str:
    """Maliyeti okunabilir string formatına çevir."""
    if cost < 0.001:
        return f"{currency}{cost:.6f}"
    elif cost < 1:
        return f"{currency}{cost:.4f}"
    else:
        return f"{currency}{cost:.2f}"


@dataclass
class ToolUsageStats:
    """Bir tool'un kullanım istatistikleri."""
    name: str = ""
    call_count: int = 0
    total_latency_ms: float = 0.0
    error_count: int = 0
    last_called: float = 0.0

    @property
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / max(self.call_count, 1)

    @property
    def error_rate(self) -> float:
        return self.error_count / max(self.call_count, 1)


class Metrics:
    """Gelişmiş agent metrik toplayıcı — token, maliyet, tool pattern'leri.

    Özellikler:
      - Token tüketimi (input/output/cached)
      - Maliyet tracking (per-call ve kümülatif)
      - Tool kullanım pattern'leri (hangi tool kaç kere, hata oranı, latency)
      - Provider bazında istatistikler
    """

    def __init__(self):
        self.token_count = 0
        self.input_tokens_total = 0
        self.output_tokens_total = 0
        self.cached_input_tokens_total = 0
        self.total_cost = 0.0
        self.request_count = 0
        self.errors = 0
        self.total_cost_per_session = 0.0
        self.session_cost: list[dict] = []
        # Tool usage tracking
        self.tool_usage: dict[str, ToolUsageStats] = {}
        # Provider tracking
        self.provider_calls: dict[str, int] = defaultdict(int)
        self.provider_cost: dict[str, float] = defaultdict(float)
        # Timing
        self.session_start: float = time.time()
        self.last_call_time: float = 0.0

    def record(
        self,
        tokens: int = 0,
        cost: float = 0.0,
        error: bool = False,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cached_input_tokens: int = 0,
        model: str | None = None,
        tool_name: str = "",
        provider: str = "",
        latency_ms: float = 0.0,
    ):
        """Bir LLM/tool çağrısını kaydet.

        cost belirtilmezse token sayılarından otomatik hesaplanır.
        """
        now = time.time()
        self.token_count += tokens
        self.input_tokens_total += input_tokens or tokens
        self.output_tokens_total += output_tokens
        self.cached_input_tokens_total += cached_input_tokens
        self.request_count += 1
        self.last_call_time = now

        if error:
            self.errors += 1

        # Cost: either given directly or calculated from tokens
        if cost > 0:
            call_cost = cost
        else:
            call_cost = calculate_tool_cost(
                input_tokens=input_tokens or tokens,
                output_tokens=output_tokens,
                cached_input_tokens=cached_input_tokens,
                model=model,
            )

        self.total_cost += call_cost
        self.total_cost_per_session += call_cost

        # Provider tracking
        if provider:
            self.provider_calls[provider] += 1
            self.provider_cost[provider] += call_cost

        # Tool usage tracking
        if tool_name:
            if tool_name not in self.tool_usage:
                self.tool_usage[tool_name] = ToolUsageStats(name=tool_name)
            stats = self.tool_usage[tool_name]
            stats.call_count += 1
            stats.total_latency_ms += latency_ms
            stats.last_called = now
            if error:
                stats.error_count += 1

        # Save session details
        entry = {
            "tool": tool_name or f"request_{self.request_count}",
            "cost": call_cost,
            "input_tokens": input_tokens or tokens,
            "output_tokens": output_tokens,
            "cached_input_tokens": cached_input_tokens,
            "model": model or settings.model.active_model or settings.model.default,
            "provider": provider,
            "latency_ms": latency_ms,
            "timestamp": now,
            "error": error,
        }
        self.session_cost.append(entry)

    def summary(self) -> dict:
        """Genel özet dict."""
        latest_model = settings.model.active_model or settings.model.default
        duration = time.time() - self.session_start
        return {
            "tokens": self.token_count,
            "input_tokens": self.input_tokens_total,
            "output_tokens": self.output_tokens_total,
            "cached_input_tokens": self.cached_input_tokens_total,
            "cost": round(self.total_cost, 6),
            "requests": self.request_count,
            "errors": self.errors,
            "total_cost_per_session": round(self.total_cost_per_session, 6),
            "model": latest_model,
            "session_calls": len(self.session_cost),
            "session_duration_sec": round(duration, 1),
            "tool_count": len(self.tool_usage),
            "providers": dict(self.provider_calls),
        }

    def tool_summary(self) -> list[dict]:
        """Tool kullanım özeti."""
        return [
            {
                "name": s.name,
                "calls": s.call_count,
                "errors": s.error_count,
                "error_rate": round(s.error_rate, 3),
                "avg_latency_ms": round(s.avg_latency_ms, 1),
                "last_called": s.last_called,
            }
            for s in sorted(self.tool_usage.values(), key=lambda x: x.call_count, reverse=True)
        ]

    def provider_summary(self) -> list[dict]:
        """Provider bazında özet."""
        return [
            {
                "provider": p,
                "calls": self.provider_calls[p],
                "cost": round(self.provider_cost[p], 6),
            }
            for p in sorted(self.provider_calls.keys())
        ]

    def format_total_cost(self) -> str:
        """Session toplam maliyetini formatlı döndür."""
        return format_cost(self.total_cost_per_session)

    def last_call_cost(self) -> float:
        """Son çağrının maliyeti."""
        if self.session_cost:
            return self.session_cost[-1]["cost"]
        return 0.0

    def to_json(self) -> str:
        """Tüm metrikleri JSON olarak dışa aktar."""
        return json.dumps({
            "summary": self.summary(),
            "tools": self.tool_summary(),
            "providers": self.provider_summary(),
            "calls": self.session_cost[-100:],  # Son 100 çağrı
        }, ensure_ascii=False)

    def reset(self):
        """Tüm metrikleri sıfırla (yeni session)."""
        self.token_count = 0
        self.input_tokens_total = 0
        self.output_tokens_total = 0
        self.cached_input_tokens_total = 0
        self.total_cost = 0.0
        self.request_count = 0
        self.errors = 0
        self.total_cost_per_session = 0.0
        self.session_cost = []
        self.tool_usage = {}
        self.provider_calls = defaultdict(int)
        self.provider_cost = defaultdict(float)
        self.session_start = time.time()
        self.last_call_time = 0.0


metrics = Metrics()
