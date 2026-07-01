"""Tool selector — tools.json cache ile hizli erisim."""
from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Any
from core.constants import DORINA_HOME

_CACHE_PATH = DORINA_HOME / "cache" / "tools.json"
_CACHE_TTL = 300  # 5 dakika


def _load_cached_tools() -> list[dict[str, Any]] | None:
    if _CACHE_PATH.exists():
        age = time.time() - _CACHE_PATH.stat().st_mtime
        if age < _CACHE_TTL:
            try:
                return json.loads(_CACHE_PATH.read_text())
            except Exception:
                pass
    return None


def _save_tools_cache(tools: list[dict[str, Any]]):
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_PATH.write_text(json.dumps(tools, ensure_ascii=False))


def get_tools(minimal: bool = False) -> list[dict[str, Any]]:
    """Tool listesini cache'den veya registry'den al.
    
    minimal=True: sadece isim + description (tool selection icin).
    minimal=False: tam şema (LLM tool calling icin).
    """
    cached = _load_cached_tools()
    if cached and not minimal:
        return cached

    from tools.registry import registry
    tools = registry.list()
    
    result = []
    for t in tools:
        entry = {"name": t.name, "description": t.description[:200]}  # description kisalt
        if not minimal:
            entry["parameters"] = t.parameters
        result.append(entry)
    
    if not minimal:
        _save_tools_cache(result)
    
    return result
