"""
MCP tools — mcp_call, mcp_list, mcp_status.

Model Context Protocol (MCP) uzerinden harici araclara erisim.
Sunucu tanimlari config.yaml'daki tools.mcp_servers bolumunden okunur.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from core.constants import DORINA_HOME
from core.logger import log
from tools.mcp.client import MCPServerConfig, mcp_manager
from tools.registry import register_tool


# ── Config yukleme ─────────────────────────────────────────

def load_mcp_config(path: Path | None = None) -> list[MCPServerConfig]:
    """config.yaml'dan MCP sunucu tanimlarini oku.

    Format (config.yaml icinde):
    ```yaml
    tools:
      mcp_servers:
        - name: filesystem
          command: npx
          args: ["-y", "@modelcontextprotocol/server-filesystem", "/home/user"]
        - name: github
          command: npx
          args: ["-y", "@modelcontextprotocol/server-github"]
    ```
    """
    import yaml

    config_path = path or DORINA_HOME / "config.yaml"
    if not config_path.exists():
        log.debug("MCP config bulunamadi, atlaniyor: %s", config_path)
        return []

    try:
        raw = yaml.safe_load(config_path.read_text()) or {}
        servers_raw = (raw.get("tools", {}) or {}).get("mcp_servers", [])
    except (yaml.YAMLError, OSError) as e:
        log.warning("MCP config okuma hatasi: %s", e)
        return []

    configs = []
    for srv in servers_raw:
        if not srv.get("enabled", True):
            continue
        try:
            configs.append(MCPServerConfig(
                name=srv["name"],
                command=srv.get("command", ""),
                args=srv.get("args", []),
                env=_resolve_env(srv.get("env", {})),
                enabled=srv.get("enabled", True),
            ))
        except (KeyError, TypeError) as e:
            log.warning("MCP sunucu config hatasi (%s): %s", srv.get("name", "?"), e)
    return configs


def _resolve_env(env: dict[str, str]) -> dict[str, str] | None:
    """Ceve ortam degiskenlerini coz. $VAR veya ${VAR} formatini destekler."""
    if not env:
        return None
    import re
    resolved = {}
    for key, val in env.items():
        if val.startswith("$"):
            var_name = val.lstrip("$").strip("{}")
            resolved[key] = os.environ.get(var_name, "")
        else:
            resolved[key] = val
    return resolved


async def startup_connect():
    """Uygulama baslangicinda MCP sunucularina baglan.

    main.py startup akisinda cagrilir.
    """
    if not _mcp_enabled():
        log.info("MCP disabled (config.yaml tools.mcp_enabled = false)")
        return

    configs = load_mcp_config()
    if not configs:
        log.info("MCP sunucu tanimi bulunamadi, atlaniyor")
        return

    for cfg in configs:
        mcp_manager.add_server(cfg)
        log.info("MCP sunucu eklendi: %s (%s)", cfg.name, cfg.command)

    await mcp_manager.connect_all()
    tools = await mcp_manager.list_all_tools()
    if tools:
        names = ", ".join(t.name for t in tools[:20])
        log.info("MCP tool'lar hazir (%d): %s", len(tools), names)
    else:
        log.info("MCP sunuculara baglanildi ama tool bulunamadi")


def _mcp_enabled() -> bool:
    try:
        from core.config import settings
        return settings.tools.mcp_enabled
    except (ImportError, AttributeError):
        return True


# ── Tool'lar ──────────────────────────────────────────────────

@register_tool(
    name="mcp_call",
    description="MCP (Model Context Protocol) uzerinden harici bir araci cagir. "
                "Ornek: dosya sistemi, GitHub, veritabani, browser. "
                "Kullanilabilir MCP araclari icin once mcp_list cagir.",
    parameters={
        "type": "object",
        "properties": {
            "tool_name": {
                "type": "string",
                "description": "Cagrilacak MCP araci adi (ornek: read_file, list_directory, create_issue)",
            },
            "arguments": {
                "type": "object",
                "description": "Araca gonderilecek parametreler (JSON object)",
                "default": {},
            },
        },
        "required": ["tool_name"],
    },
    toolset="mcp",
)
async def mcp_call_tool(tool_name: str, arguments: dict = None) -> str:
    """MCP aracini cagir. tool_name ile hangi MCP sunucusundaki hangi arac
    oldugunu belirt, arguments ile parametreleri gec.

    Ornek:
        mcp_call(tool_name="read_file", arguments={"path": "/home/user/file.txt"})
        mcp_call(tool_name="search_files", arguments={"pattern": "*.py", "path": "."})
    """
    if not mcp_manager.servers:
        return json.dumps({
            "error": "Hicbir MCP sunucusu bagli degil. "
                     "config.yaml'da tools.mcp_servers bolumunu ekle.",
        })

    try:
        # Ilk seferde tool cache'ini olustur
        if not hasattr(mcp_call_tool, "_tool_cache"):
            mcp_call_tool._tool_cache = {}
            all_tools = await mcp_manager.list_all_tools()
            for t in all_tools:
                mcp_call_tool._tool_cache[t.name] = t

        # Tool cache'de var mi?
        mcp_tool = mcp_call_tool._tool_cache.get(tool_name)
        if not mcp_tool:
            return json.dumps({
                "error": f"MCP araci bulunamadi: '{tool_name}'. "
                         f"Kullanilabilir: {', '.join(sorted(mcp_call_tool._tool_cache.keys()))}",
                "available_tools": list(mcp_call_tool._tool_cache.keys()),
            })

        result = await mcp_manager.call_tool(tool_name, arguments or {})
        return result

    except (asyncio.TimeoutError, ConnectionError, OSError) as e:
        return json.dumps({"error": f"MCP hatasi: {e}"})


@register_tool(
    name="mcp_list",
    description="Bagli MCP sunucularindaki kullanilabilir araclari listele. "
                "Hangi MCP araclarinin var oldugunu gormek icin kullan.",
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
    toolset="mcp",
)
async def mcp_list_tool() -> str:
    """Bagli MCP sunucularini ve tool'larini listele."""
    if not mcp_manager.servers:
        return json.dumps({
            "servers": [],
            "message": "Hicbir MCP sunucusu bagli degil. "
                       "config.yaml'da tools.mcp_servers bolumunu ekle.",
        })

    result = {
        "servers": [],
        "total_tools": 0,
    }

    for name, client in mcp_manager.servers.items():
        connected = client._connected
        tools = []
        if connected:
            try:
                tools_data = await client.list_tools()
                tools = [{"name": t.name, "description": t.description} for t in tools_data]
            except (OSError, asyncio.TimeoutError):
                pass

        result["servers"].append({
            "server": name,
            "connected": connected,
            "command": client.config.command,
            "tool_count": len(tools),
            "tools": tools,
        })
        result["total_tools"] += len(tools)

    return json.dumps(result, ensure_ascii=False, indent=2)


@register_tool(
    name="mcp_status",
    description="MCP sunucu baglanti durumunu goster. Hangi sunucularin bagli oldugunu kontrol et.",
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
    toolset="mcp",
)
async def mcp_status_tool() -> str:
    """MCP sunucu baglanti durumu."""
    if not mcp_manager.servers:
        return json.dumps({
            "status": "no_servers",
            "message": "Hicbir MCP sunucusu yapilandirilmamis.",
        })

    ping_results = await mcp_manager.ping_all()
    servers = []
    for name, alive in ping_results.items():
        servers.append({
            "name": name,
            "connected": alive,
        })

    return json.dumps({
        "status": "connected" if any(ping_results.values()) else "disconnected",
        "server_count": len(servers),
        "servers": servers,
    }, ensure_ascii=False)
