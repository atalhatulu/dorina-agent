"""Metrics hook — tool çağrı istatistiklerini toplar.

Pre-execution: çağrı sayacını artırır
Post-processing: süre ve sonuç boyutunu kaydeder
"""
from __future__ import annotations
import time
from collections import defaultdict
from core.logger import log


class MetricsCollector:
    """Tool metrikleri toplayıcı — thread-safe değil, tek thread için."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.call_counts: dict[str, int] = defaultdict(int)
        self.error_counts: dict[str, int] = defaultdict(int)
        self.total_duration: float = 0.0
        self.call_durations: dict[str, list[float]] = defaultdict(list)
        self._start_times: dict[str, float] = {}

    def on_pre_execution(self, tool_name: str, arguments: dict) -> bool | None:
        """Çağrı sayacını artır ve zamanı başlat."""
        self.call_counts[tool_name] += 1
        self._start_times[tool_name] = time.time()
        return None  # iptal yok

    def on_post_processing(self, tool_name: str, arguments: dict, result: str) -> str:
        """Süreyi kaydet."""
        start = self._start_times.pop(tool_name, None)
        if start is not None:
            duration = time.time() - start
            self.total_duration += duration
            self.call_durations[tool_name].append(duration)
        return result

    def on_error(self, tool_name: str, error: str) -> None:
        """Hata sayacını artır."""
        self.error_counts[tool_name] += 1

    def summary(self) -> dict:
        """Metrik özeti döndür."""
        return {
            "total_calls": sum(self.call_counts.values()),
            "total_errors": sum(self.error_counts.values()),
            "total_duration_sec": round(self.total_duration, 3),
            "calls_by_tool": dict(self.call_counts),
            "errors_by_tool": dict(self.error_counts),
            "avg_duration_by_tool": {
                tool: round(sum(durs) / len(durs), 3)
                for tool, durs in self.call_durations.items()
            },
        }


# Global metrics collector
metrics = MetricsCollector()
