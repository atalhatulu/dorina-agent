"""Re-export hub for builtin tools.

All tools from terminal.py, file_tools.py, and web_tools.py are re-exported
here so existing imports (from tools.builtin.basic import ...) continue to work.
"""

from __future__ import annotations
import json

from tools.registry import register_tool

# ── Re-export all tools from split modules ──────────────────

from tools.builtin.terminal import (
    terminal_tool,
    batch_python_tool,
    _sandbox_enabled_in_config,
    _run_in_sandbox,
    _run_python_in_sandbox,
)
from tools.builtin.file_tools import (
    read_file_tool,
    write_file_tool,
    search_files_tool,
    patch_tool,
    _search_file_broad,
)
from tools.builtin.web_tools import (
    web_search_tool,
    web_fetch_tool,
)


# ─── TOOLSET YONETIMI ────────────────────────────────────

@register_tool(
    name="tools_enable",
    description="Yeni bir tool kategorisini aktiflestir. Kategoriler: file, web, terminal, delegation, system, mcp.",
    parameters={
        "type": "object",
        "properties": {
            "toolset": {
                "type": "string",
                "description": "Aktiflestirilecek kategori. En cok kullanilan: delegation, mcp, system",
                "enum": ["file", "web", "terminal", "delegation", "mcp", "system"],
            }
        },
        "required": ["toolset"],
    },
    toolset="system",
)
def tools_enable_tool(toolset: str) -> str:
    from tools.toolset import tools_enable
    return tools_enable(toolset)
