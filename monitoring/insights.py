"""Insight Engine — hata istatistikleri, trend analizi, performans değerlendirmesi.

Özellikler:
  - Hata istatistikleri: en çok hata alan tool'lar, hata kategorileri
  - Trend analizi: token tüketimi, maliyet, çağrı sayısı trend'i
  - Performans: ortalama latency, error rate, tool verimliliği
  - Öneriler: iyileştirme önerileri (örneğin: "X tool'u çok hata alıyor")
"""
from __future__ import annotations
import time
from typing import Optional
from collections import defaultdict, Counter
from dataclasses import dataclass, field

from core.logger import log
from core.event_bus import bus


@dataclass
class ErrorRecord:
    """Bir hata kaydı."""
    tool_name: str
    error_message: str
    error_type: str = "unknown"
    timestamp: float = 0.0
    context: dict = field(default_factory=dict)


@dataclass
class TrendPoint:
    """Trend veri noktası."""
    timestamp: float = 0.0
    token_count: int = 0
    cost: float = 0.0
    call_count: int = 0
    error_count: int = 0
    avg_latency_ms: float = 0.0


class InsightsEngine:
    """Insight engine — metrik verilerini analiz eder ve öngörüler üretir.

    Event bus üzerinden gelen verileri işler:
      - tool:called → kullanım sayacı
      - tool:error → hata kaydı
      - tool:executed → başarılı çağrı
    """

    def __init__(self):
        # Error tracking
        self.error_log: list[ErrorRecord] = []
        self.error_by_tool: dict[str, int] = defaultdict(int)
        self.error_by_type: dict[str, int] = defaultdict(int)
        # Trend data (son 1000 nokta)
        self.trend: list[TrendPoint] = []
        self._trend_window = 1000
        # Timing
        self.last_error_time: float = 0.0
        self.error_rate_window: list[tuple[float, bool]] = []  # (timestamp, is_error)

    def record_error(self, tool_name: str, error_message: str,
                     error_type: str = "unknown", context: dict | None = None):
        """Bir hatayı kaydet."""
        record = ErrorRecord(
            tool_name=tool_name,
            error_message=str(error_message)[:500],
            error_type=error_type,
            timestamp=time.time(),
            context=context or {},
        )
        self.error_log.append(record)
        self.error_by_tool[tool_name] += 1
        self.error_by_type[error_type] += 1
        self.last_error_time = record.timestamp
        self.error_rate_window.append((record.timestamp, True))

        # Limit error log size
        if len(self.error_log) > 1000:
            self.error_log = self.error_log[-500:]

        # Clean old error rate window entries (last 5 min)
        self._clean_error_rate_window()

    def record_call(self, success: bool = True, tokens: int = 0,
                    cost: float = 0.0, latency_ms: float = 0.0):
        """Bir çağrıyı trend verisine kaydet."""
        now = time.time()
        self.error_rate_window.append((now, not success))
        self._clean_error_rate_window()

        point = TrendPoint(
            timestamp=now,
            token_count=tokens,
            cost=cost,
            call_count=1,
            error_count=0 if success else 1,
            avg_latency_ms=latency_ms,
        )
        self.trend.append(point)
        if len(self.trend) > self._trend_window:
            self.trend = self.trend[-self._trend_window:]

    def _clean_error_rate_window(self, window_sec: int = 300):
        """5 dakikadan eski error rate kayıtlarını temizle."""
        cutoff = time.time() - window_sec
        self.error_rate_window = [
            e for e in self.error_rate_window if e[0] > cutoff
        ]

    @property
    def current_error_rate(self) -> float:
        """Son 5 dakikadaki hata oranı."""
        if not self.error_rate_window:
            return 0.0
        errors = sum(1 for _, err in self.error_rate_window if err)
        return errors / len(self.error_rate_window)

    def most_error_prone_tools(self, top_n: int = 5) -> list[dict]:
        """En çok hata alan tool'lar."""
        sorted_tools = sorted(
            self.error_by_tool.items(),
            key=lambda x: x[1],
            reverse=True,
        )
        return [
            {"tool": tool, "errors": count}
            for tool, count in sorted_tools[:top_n]
        ]

    def most_common_errors(self, top_n: int = 5) -> list[dict]:
        """En sık karşılaşılan hata tipleri."""
        sorted_types = sorted(
            self.error_by_type.items(),
            key=lambda x: x[1],
            reverse=True,
        )
        return [
            {"type": etype, "count": count}
            for etype, count in sorted_types[:top_n]
        ]

    def token_trend(self, window: int = 10) -> list[dict]:
        """Token tüketim trend'i (son N nokta)."""
        points = self.trend[-window:]
        return [
            {
                "timestamp": p.timestamp,
                "tokens": p.token_count,
                "cost": p.cost,
            }
            for p in points
        ]

    def cost_trend(self, window: int = 10) -> list[dict]:
        """Maliyet trend'i."""
        points = self.trend[-window:]
        return [
            {
                "timestamp": p.timestamp,
                "cost": p.cost,
            }
            for p in points
        ]

    def performance_summary(self) -> dict:
        """Performans özeti."""
        if not self.trend:
            return {
                "total_calls": 0,
                "total_errors": 0,
                "error_rate": 0.0,
                "avg_latency_ms": 0.0,
                "total_cost": 0.0,
                "total_tokens": 0,
            }

        total_calls = sum(p.call_count for p in self.trend)
        total_errors = sum(p.error_count for p in self.trend)
        total_cost = sum(p.cost for p in self.trend)
        total_tokens = sum(p.token_count for p in self.trend)
        latencies = [p.avg_latency_ms for p in self.trend if p.avg_latency_ms > 0]

        return {
            "total_calls": total_calls,
            "total_errors": total_errors,
            "error_rate": round(total_errors / max(total_calls, 1), 4),
            "avg_latency_ms": round(sum(latencies) / max(len(latencies), 1), 1) if latencies else 0.0,
            "total_cost": round(total_cost, 6),
            "total_tokens": total_tokens,
        }

    def recommendations(self) -> list[str]:
        """İyileştirme önerileri üret."""
        recs = []

        # Hata oranı yüksekse
        err_rate = self.current_error_rate
        if err_rate > 0.2:
            recs.append(f"⚠️ Hata oranı %%{err_rate*100:.0f} — çok yüksek. Provider veya model değiştirmeyi düşünün.")

        # En çok hata alan tool
        bad_tools = self.most_error_prone_tools(3)
        for bt in bad_tools:
            if bt["errors"] >= 3:
                recs.append(f"🔧 '{bt['tool']}' aracı {bt['errors']} kez hata aldı — parametreleri kontrol edin.")

        # Sık karşılaşılan hata tipleri
        common = self.most_common_errors(3)
        for c in common:
            if c["count"] >= 3:
                recs.append(f"📊 '{c['type']}' tipi hata {c['count']} kez görüldü.")

        if not recs:
            recs.append("✅ Şu ana kadar önemli bir sorun tespit edilmedi.")

        return recs

    def full_report(self) -> dict:
        """Kapsamlı insight raporu."""
        return {
            "performance": self.performance_summary(),
            "error_rate_5min": self.current_error_rate,
            "error_prone_tools": self.most_error_prone_tools(),
            "common_errors": self.most_common_errors(),
            "recommendations": self.recommendations(),
            "total_errors_logged": len(self.error_log),
            "trend_points": len(self.trend),
        }


# Global instance
insights = InsightsEngine()


# ── Event bus handlers ─────────────────────────────────────

def _on_tool_called(event: str = "", **kw):
    """Tool çağrısı event'ini dinle."""
    pass  # Başarılı çağrıları da kaydetmek için


def _on_tool_error(event: str = "", **kw):
    """Tool hatası event'ini dinle ve insight'a kaydet."""
    insights.record_error(
        tool_name=kw.get("name", "unknown"),
        error_message=kw.get("error", str(kw)),
        error_type="tool_error",
    )


def _on_tool_executed(event: str = "", **kw):
    """Başarılı tool çağrısını kaydet."""
    insights.record_call(
        success=True,
        tokens=len(str(kw.get("result", ""))),
        latency_ms=0,
    )


# Subscribe to events
def register_insight_hooks():
    """Event bus'a insight hook'larını kaydet."""
    from core.event_bus import bus
    bus.subscribe("tool:error", _on_tool_error)
    bus.subscribe("tool:executed", _on_tool_executed)
    bus.subscribe("tool:called", _on_tool_called)
    log.info("Insight hooks registered on event bus")
