"""
Active toolset manager — replaces the old ChromaDB-based selector.

Instead of sending every tool to the LLM each turn, only active toolset
tools are sent. The agent opens new toolsets via tools_enable() as needed.

Default: FILE + WEB (most frequently used)
"""

from __future__ import annotations
from typing import Optional

# ── Active toolsets ───────────────────────────────────────
# Opened by default at session start — read from config.yaml tools.default_toolsets
try:
    from core.config import settings
    _cfg_tools = getattr(settings, "tools", None)
    if _cfg_tools and hasattr(_cfg_tools, "default_toolsets") and _cfg_tools.default_toolsets:
        DEFAULT_TOOLSETS = set(t.lower().strip() for t in _cfg_tools.default_toolsets)
    else:
        DEFAULT_TOOLSETS = {"file", "web", "terminal"}
except (AttributeError, ImportError):
    DEFAULT_TOOLSETS = {"file", "web", "terminal"}

ACTIVE_TOOLSETS: set[str] = set(DEFAULT_TOOLSETS)

# ── Toolset labels (shown in system prompt) ───────────────
TOOLSET_LABELS = {
    "file":        "📁 FILE       — read, write, patch, search, batch_python",
    "web":         "🌐 WEB        — web_search, web_fetch",
    "terminal":    "💻 TERMINAL   — shell commands",
    "delegation":  "🤖 AGENT      — delegate_task, delegate_batch, delegate_goal",
    "mcp":         "🔌 MCP        — mcp_call, mcp_list, mcp_status",
    "system":      "⚙️ SYSTEM     — tools_enable, cron, save_memory, read_memory",
}

ACTIVE_TOOLSET_LABELS = {k: v for k, v in TOOLSET_LABELS.items() if k in DEFAULT_TOOLSETS}


def tools_enable(toolset: str) -> str:
    """Add a new toolset to the active list."""
    normalized = toolset.lower().strip()
    if normalized not in TOOLSET_LABELS:
        available = ", ".join(sorted(TOOLSET_LABELS.keys()))
        return f"❌ Unknown toolset: '{toolset}'. Available: {available}"
    if normalized in ACTIVE_TOOLSETS:
        return f"ℹ️  '{toolset}' already active."
    ACTIVE_TOOLSETS.add(normalized)
    return f"✅ '{toolset}' enabled. {TOOLSET_LABELS.get(normalized, '')}"


def tools_disable(toolset: str) -> str:
    """Remove a toolset from the active list."""
    normalized = toolset.lower().strip()
    if normalized not in ACTIVE_TOOLSETS:
        return f"ℹ️  '{toolset}' not currently active."
    if normalized in DEFAULT_TOOLSETS:
        return f"⚠️  '{toolset}' is a default toolset and cannot be disabled."
    ACTIVE_TOOLSETS.discard(normalized)
    return f"✅ '{toolset}' disabled."


def get_active_toolsets() -> frozenset[str]:
    """Return currently active toolsets."""
    return frozenset(ACTIVE_TOOLSETS)


def get_active_schemas(user_input: str = "") -> list[dict]:
    """Return schemas for tools in active toolsets.
    If the task is read-only, only reading tools are sent (token savings).

    tools_enable is always included (belongs to the system toolset but stays open as a meta-tool)."""
    from tools.registry import registry

    # Is the task read-only? (inspect, review, audit, search, etc.)
    _readonly_keywords = {"incele", "analiz", "kontrol", "bak", "goster", "listele", "ara", "oku", "audit", "review", "inspect", "ne yap", "nasil", "açıkla", "anlat"}
    _is_readonly = any(k in user_input.lower() for k in _readonly_keywords) if user_input else False

    active = get_active_toolsets()
    schemas = []
    for tool in registry.list():
        # tools_enable always active (meta-tool)
        if tool.name == "tools_enable":
            schemas.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            })
            continue
        if tool.toolset not in active:
            continue
        # Read-only task: only reading tools
        if _is_readonly and tool.name not in {
            "read_file", "search_files", "web_search", "web_fetch",
            "terminal",
        }:
            continue
        schemas.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        })
    return schemas


def toolset_summary() -> str:
    """Category list shown in system prompt."""
    lines = ["## AVAILABLE TOOLS"]
    lines.append("Each tool belongs to a category. Use tools_enable to open the category you need.")
    lines.append("")
    for key in sorted(TOOLSET_LABELS.keys()):
        label = TOOLSET_LABELS[key]
        status = "✅" if key in ACTIVE_TOOLSETS else "🔒"
        lines.append(f"  {status} {label}")
    lines.append("")
    lines.append("📌 Default: FILE, WEB, TERMINAL. tools_enable('delegation') to add AGENT, tools_enable('mcp') to add GITHUB. tools_enable is always available.")
    return "\n".join(lines)


def reset():
    """Reset at session end."""
    ACTIVE_TOOLSETS.clear()
    ACTIVE_TOOLSETS.update(DEFAULT_TOOLSETS)
