"""Logging hook — tool çağrılarını loglar.

Pre-execution: tool çağrısını loglar
Post-processing: tool sonucunu loglar (truncated)
"""
from __future__ import annotations
from core.logger import log


def log_pre_execution(tool_name: str, arguments: dict) -> bool | None:
    """Tool çağrısı öncesi logla. Hiçbir zaman iptal etmez."""
    arg_summary = {k: (str(v)[:100] if isinstance(v, str) else v) for k, v in arguments.items()}
    log.info(f"[HOOK] Tool çağrılıyor: {tool_name}, args={arg_summary}")
    return None  # iptal yok


def log_post_processing(tool_name: str, arguments: dict, result: str) -> str:
    """Tool sonucunu logla (büyük sonuçları truncate et)."""
    truncated = result[:500] + "..." if len(result) > 500 else result
    log.info(f"[HOOK] Tool tamamlandı: {tool_name}, result_len={len(result)}, result={truncated}")
    return result  # sonucu değiştirme


def log_error(tool_name: str, error: str) -> None:
    """Tool hatasını logla."""
    log.error(f"[HOOK] Tool hatası: {tool_name}, error={error[:300]}")
