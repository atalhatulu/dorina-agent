"""MCP (Model Context Protocol) — external tool integration."""

from __future__ import annotations

from tools.mcp.client import (
    MCPClient,
    MCPManager,
    MCPServerConfig,
    MCPToolDef,
    mcp_manager,
)

__all__ = [
    "MCPClient",
    "MCPManager",
    "MCPServerConfig",
    "MCPToolDef",
    "mcp_manager",
]
