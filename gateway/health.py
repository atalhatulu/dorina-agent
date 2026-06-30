"""Health check — provider connectivity, memory, sandbox status.

Used by the gateway /health endpoint and can be called independently.
"""

from __future__ import annotations

import time
import importlib

from core.constants import VERSION


_start_time: float = time.time()


def get_uptime() -> float:
    """Seconds since module load."""
    return time.time() - _start_time


def check_providers() -> dict[str, bool]:
    """Check which LLM providers have keys configured."""
    results: dict[str, bool] = {}
    try:
        from providers.keys import keys, PROVIDERS
        for name, info in PROVIDERS.items():
            env_var = info.get("env", "")
            if not env_var:
                results[name] = True  # no-env providers (e.g. ollama) are "available"
            else:
                val = keys.get_key(name)
                results[name] = bool(val)
    except Exception:
        results["error"] = False
    return results


def check_memory() -> dict[str, bool]:
    """Check memory subsystem health."""
    results: dict[str, bool] = {}
    try:
        # Semantic memory (ChromaDB)
        from memory.semantic import SemanticMemory
        sm = SemanticMemory()
        sm.collection.count()
        results["semantic"] = True
    except Exception:
        results["semantic"] = False

    try:
        from memory.procedural import ProceduralMemory
        pm = ProceduralMemory()
        results["procedural"] = True
    except Exception:
        results["procedural"] = False

    try:
        from memory.episodic import EpisodicMemory
        em = EpisodicMemory()
        results["episodic"] = True
    except Exception:
        results["episodic"] = False

    return results


def check_sandbox() -> bool:
    """Check if Docker sandbox is available."""
    try:
        from security.sandbox import sandbox
        return sandbox.available if hasattr(sandbox, "available") else False
    except Exception:
        return False


def check_tools() -> bool:
    """Check if tool registry loaded successfully."""
    try:
        from tools.registry import registry
        return registry.count() > 0
    except Exception:
        return False


def get_health() -> dict:
    """Full health check dict."""
    providers = check_providers()
    memory = check_memory()
    sandbox_ok = check_sandbox()

    all_providers_ok = all(providers.values())
    all_memory_ok = all(memory.values())

    if all_providers_ok and all_memory_ok:
        status = "ok"
    elif not all_providers_ok and not all_memory_ok:
        status = "error"
    else:
        status = "degraded"

    return {
        "status": status,
        "version": VERSION,
        "providers": providers,
        "memory": memory,
        "sandbox": sandbox_ok,
        "uptime_seconds": get_uptime(),
        "tools_loaded": check_tools(),
    }
