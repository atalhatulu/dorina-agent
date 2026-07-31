"""Active toolset manager — replaces the old ChromaDB-based selector.

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


def _classify_query(user_input: str) -> str:
    """Classify query into: 'read', 'chat', 'code', 'general'."""
    if not user_input or not user_input.strip():
        return "general"
    text = user_input.lower().strip()

    # Read-only info queries — only need WEB
    read_patterns = [
        "hava durumu", "weather", "haber", "news", "nedir", "ne demek",
        "nasil", "how to", "what is", "who is", "where", "when",
        "saat", "time", "tarih", "date", "fiyat", "price", "kac",
        "indir", "download", "oku", "read",
        "internet", "web", "online", "sitede", "sayfasinda",
    ]
    if any(p in text for p in read_patterns) and len(text.split()) <= 6:
        return "read"

    # Code tasks — need file + terminal (check BEFORE chat — 'dosya ara' is not a greeting)
    code_patterns = ["kod", "code", "yaz", "write", "olustur", "create",
                     "build", "compile", "refactor", "duzelt", "fix",
                     "debug", "hata", "error", "bug", "test", "patch",
                     "fonksiyon", "function", "class", "import",
                     "dosya", "kac tane", "say", "liste", "list",
                     "tara", "goster", "bul", "ara", "grep", "klasor",
                     "dizin", "python", "py dosyas"]
    if any(p in text for p in code_patterns):
        return "code"

    # Chat/greeting — minimal tools
    chat_patterns = ["merhaba", "selam", "hey", "nasilsin", "naber",
                     "tesekkur", "thanks", "gorusuruz", "bye", "hello"]
    if text in chat_patterns or (
        len(text.split()) <= 3 and not any(c in text for c in "./\\")
    ):
        return "chat"
    # Also: if starts with a greeting word and has no tool-like patterns
    first_word = text.split()[0] if text.split() else ""
    if first_word in {"merhaba", "selam", "hey", "hello", "hi", "selamun aleykum"}:
        return "chat"

    return "general"


def get_active_schemas(user_input: str = "") -> list[dict]:
    """Return schemas for tools — smart selection based on query type.

    Classifies the query to only send relevant tool schemas, saving tokens.
    tools_enable is always included so the agent can open more toolsets if needed.
    """
    from tools.registry import registry

    # Classify query to pick relevant toolsets
    qtype = _classify_query(user_input)
    query_toolsets = {
        "read":    {"web"},
        "chat":    set(),       # no tools needed for greetings
        "code":    {"file", "terminal"},
        "general": get_active_toolsets(),
    }
    needed = query_toolsets.get(qtype, get_active_toolsets())
    # Always include system toolset (tools_enable, cron, etc.)
    needed = needed | {"system"}

    schemas = []
    for tool in registry.list():
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
        if tool.toolset not in needed:
            continue
        # Inject project directory into terminal's cwd param — agent runs commands in the right place
        params = tool.parameters
        if tool.name == "terminal" and isinstance(params, dict):
            import copy
            params = copy.deepcopy(params)
            _proj = _get_project_dir()
            if _proj:
                cwd_desc = params.get("properties", {}).get("cwd", {}).get("description", "Working directory (Optional)")
                params["properties"]["cwd"]["description"] = f"{cwd_desc}. DEFAULT: {_proj} — project files live here. Use it unless the user asks about elsewhere."
        schemas.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": params,
            },
        })
    return schemas


def _get_project_dir() -> str:
    """Return user's project directory from profile, or empty string."""
    try:
        from core.constants import DORINA_HOME
        p = DORINA_HOME / "user_profile.json"
        if p.exists():
            import json
            prof = json.loads(p.read_text())
            return prof.get("project_dir", "")
    except Exception:
        pass
    return ""


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
