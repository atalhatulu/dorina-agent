"""
Active toolset manager — replaces the old ChromaDB-based selector.

LLM'e her turda tüm tool'ları göndermek yerine, sadece aktif toolset'lerin
tool'ları gönderilir. Agent ihtiyaç duydukça tools_enable() ile yeni toolset açar.

Default: FILE + WEB (en sık kullanılanlar)
"""

from __future__ import annotations
from typing import Optional

# ── Aktif toolset'ler ─────────────────────────────────────
# Session başında default olarak açık olanlar — config.yaml tools.default_toolsets'den okunur
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

# ── Toolset tanımları (system prompt'ta gösterilecek) ─────
TOOLSET_LABELS = {
    "file":      "📁 FILE    — read, write, patch, search, batch_python",
    "web":       "🌐 WEB     — web_search, web_fetch",
    "terminal":  "💻 TERMINAL — shell commands",
    "git":       "📋 GIT     — add, commit, diff, branch, push, status, log",
    "memory":    "🧠 MEMORY  — save_memory, read_memory",
    "cron":      "⏰ CRON    — add, remove, list, clear",
    "delegation": "🤖 AGENT   — delegate_task, delegate_batch, clarify",
    "sandbox":   "🐳 SANDBOX — sandbox_exec (isolated execution)",
    "graphify":  "📊 GRAPH   — codebase analysis (import/call graph)",
    "research":  "🔬 RESEARCH — deep_research, browser_navigate",
    "vision":    "👁️ VISION  — analyze_image",
    "mcp":       "🔗 MCP     — mcp_call_tool (external tools)",
    "system":    "⚙️ SYSTEM  — list_providers, switch_provider, background tasks",
}

ACTIVE_TOOLSET_LABELS = {k: v for k, v in TOOLSET_LABELS.items() if k in DEFAULT_TOOLSETS}


def tools_enable(toolset: str) -> str:
    """Aktif toolset listesine yeni bir toolset ekler."""
    normalized = toolset.lower().strip()
    if normalized not in TOOLSET_LABELS:
        available = ", ".join(sorted(TOOLSET_LABELS.keys()))
        return f"❌ Bilinmeyen toolset: '{toolset}'. Kullanılabilir: {available}"
    if normalized in ACTIVE_TOOLSETS:
        return f"ℹ️  '{toolset}' zaten aktif."
    ACTIVE_TOOLSETS.add(normalized)
    return f"✅ '{toolset}' toolset'i aktifleştirildi. {TOOLSET_LABELS.get(normalized, '')}"


def tools_disable(toolset: str) -> str:
    """Aktif toolset listesinden bir toolset çıkarır."""
    normalized = toolset.lower().strip()
    if normalized not in ACTIVE_TOOLSETS:
        return f"ℹ️  '{toolset}' zaten aktif değil."
    if normalized in DEFAULT_TOOLSETS:
        return f"⚠️  '{toolset}' default bir toolset, kapatılamaz."
    ACTIVE_TOOLSETS.discard(normalized)
    return f"✅ '{toolset}' devre dışı bırakıldı."


def get_active_toolsets() -> frozenset[str]:
    """Şu an aktif olan toolset'leri döndürür."""
    return frozenset(ACTIVE_TOOLSETS)


def get_active_schemas(user_input: str = "") -> list[dict]:
    """Aktif toolset'lerdeki tool'larin schema'larini dondurur.
    Gorev salt-okunur tespit edilirse sadece okuma tool'lari gonderilir (token tasarrufu)."""
    from tools.registry import registry
    
    # Gorev salt-okunur mu? (incele, analiz, bak, oku, listele, ara, audit, review)
    _readonly_keywords = {"incele", "analiz", "kontrol", "bak", "goster", "listele", "ara", "oku", "audit", "review", "inspect", "ne yap", "nasil", "açıkla", "anlat"}
    _is_readonly = any(k in user_input.lower() for k in _readonly_keywords) if user_input else False
    
    active = get_active_toolsets()
    schemas = []
    for tool in registry.list():
        if tool.toolset in active:
            # Salt-okunur gorev: sadece okuma araclari
            if _is_readonly and tool.name not in {
                "read_file", "search_files", "web_search", "web_fetch",
                "list_directory", "terminal",
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
    """System prompt'ta gösterilecek kategori listesi."""
    lines = ["## KULLANILABILIR ARACLAR"]
    lines.append("Her araç bir kategoriye aittir. İhtiyacın olan kategoriyi tools_enable ile aç.")
    lines.append("")
    for key in sorted(TOOLSET_LABELS.keys()):
        label = TOOLSET_LABELS[key]
        status = "✅" if key in ACTIVE_TOOLSETS else "🔒"
        lines.append(f"  {status} {label}")
    lines.append("")
    lines.append("📌 Default açık: FILE + WEB + TERMINAL. tools_enable('GIT') ile yeni kategori eklersin.")
    return "\n".join(lines)


def reset():
    """Session sonunda sıfırla."""
    ACTIVE_TOOLSETS.clear()
    ACTIVE_TOOLSETS.update(DEFAULT_TOOLSETS)
