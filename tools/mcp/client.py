"""
MCP Client — Model Context Protocol client.

Model Context Protocol (MCP) enables AI agents to connect to external tools
and data sources via a standard protocol. This module connects to MCP servers,
discovers their tools, and calls them.

Reference: https://github.com/modelcontextprotocol/python-sdk
Adaptation: python-sdk/src/mcp/client/ (MIT License)
"""

from __future__ import annotations
import asyncio
import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from typing import Any, Optional

from core.logger import log

logger = logging.getLogger(__name__)


@dataclass
class MCPToolDef:
    """Tool definition from an MCP server."""
    name: str
    description: str
    input_schema: dict
    server_name: str


@dataclass
class MCPServerConfig:
    """MCP server configuration."""
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] | None = None
    enabled: bool = True


class MCPClient:
    """
    Connects to an MCP server, discovers its tools, and calls them.

    Usage:
        client = MCPClient(config)
        await client.connect()
        tools = await client.list_tools()
        result = await client.call_tool("tool_name", {"param": "value"})
        await client.disconnect()
    """

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self.process: subprocess.Popen | None = None
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self._request_id = 0
        self._pending: dict[str, asyncio.Future] = {}
        self._reader_task: asyncio.Task | None = None
        self._stderr_task: asyncio.Task | None = None
        self._connected = False
        self._server_info: dict = {}

    async def connect(self):
        """Connect to MCP server (stdio transport)."""
        if self._connected:
            return

        try:
            # Resolve $VAR references in env and inherit PATH
            resolved_env = None
            if self.config.env:
                resolved_env = {**os.environ}
                for k, v in self.config.env.items():
                    if isinstance(v, str) and v.startswith("$"):
                        resolved_env[k] = os.environ.get(v[1:], v)
                    else:
                        resolved_env[k] = v
            elif os.environ.get("GITHUB_TOKEN") or os.environ.get("ANTHROPIC_API_KEY"):
                resolved_env = {**os.environ}
            else:
                resolved_env = os.environ.copy()

            # Start subprocess
            self.process = await asyncio.create_subprocess_exec(
                self.config.command,
                *self.config.args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=resolved_env,
            )

            # Python 3.12+ create_subprocess_exec returns StreamReader/StreamWriter directly
            if self.process.stdout is None or self.process.stdin is None:
                raise ConnectionError("Subprocess pipes not available")
            self.reader = self.process.stdout  # already a StreamReader
            self.writer = self.process.stdin   # already a StreamWriter
            self._connected = True

            # Log stderr in background
            self._stderr_task = asyncio.create_task(self._log_stderr())

            # JSON-RPC reader task
            self._reader_task = asyncio.create_task(self._read_loop())

            # Start communication — send initialize request
            result = await self._request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "dorina-agent",
                    "version": "1.0.0",
                },
            })

            initialized = json.loads(result)
            self._server_info = initialized

            # Initialized notification
            await self._notify("notifications/initialized")

            log.info(f"MCP connected: {self.config.name} ({self.config.command})")

        except (subprocess.CalledProcessError, OSError, asyncio.TimeoutError, json.JSONDecodeError) as e:
            log.error(f"MCP connection error [{self.config.name}]: {e}")
            await self.disconnect()
            raise

    async def disconnect(self):
        """Disconnect from MCP server."""
        self._connected = False

        if self._reader_task:
            self._reader_task.cancel()
            self._reader_task = None

        if self._stderr_task:
            self._stderr_task.cancel()
            self._stderr_task = None

        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except (OSError, ConnectionError):
                pass
            self.writer = None

        if self.process:
            try:
                self.process.terminate()
                await asyncio.sleep(0.5)
                if self.process.returncode is None:
                    self.process.kill()
                await self.process.wait()
            except (OSError, ProcessLookupError):
                pass
            self.process = None

        log.info(f"MCP disconnected: {self.config.name}")

    async def list_tools(self) -> list[MCPToolDef]:
        """List tools from the server."""
        if not self._connected:
            return []

        try:
            result = await self._request("tools/list", {})
            data = json.loads(result)
            tools_data = data.get("tools", data.get("result", {}).get("tools", []))

            return [
                MCPToolDef(
                    name=t.get("name"),
                    description=t.get("description", ""),
                    input_schema=t.get("inputSchema", {}),
                    server_name=self.config.name,
                )
                for t in tools_data
            ]

        except (json.JSONDecodeError, KeyError, TypeError, OSError) as e:
            log.error(f"MCP tool listing error: {e}")
            return []

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Call an MCP tool."""
        if not self._connected:
            return json.dumps({"error": "Not connected to MCP server"})

        try:
            result = await self._request("tools/call", {
                "name": tool_name,
                "arguments": arguments,
            })
            data = json.loads(result)

            # Convert content to plain text
            content_parts = []
            result_data = data.get("result", data)
            for item in result_data.get("content", []):
                if item.get("type") == "text":
                    content_parts.append(item.get("text", ""))
                elif item.get("type") == "resource":
                    content_parts.append(str(item.get("resource", "")))

            return "\n".join(content_parts) if content_parts else json.dumps(data)

        except (json.JSONDecodeError, KeyError, TypeError, OSError) as e:
            return json.dumps({"error": str(e)})

    async def ping(self) -> bool:
        """Ping the server."""
        try:
            await self._request("ping", {})
            return True
        except (OSError, asyncio.TimeoutError):
            return False

    async def _request(self, method: str, params: dict) -> str:
        """Send a JSON-RPC request."""
        self._request_id += 1
        req_id = str(self._request_id)

        request = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }

        future = asyncio.get_event_loop().create_future()
        self._pending[req_id] = future

        line = json.dumps(request, ensure_ascii=False) + "\n"
        self.writer.write(line.encode("utf-8"))
        await self.writer.drain()

        try:
            return await asyncio.wait_for(future, timeout=60)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise TimeoutError(f"MCP request timeout: {method}")

    async def _log_stderr(self):
        """Log MCP server stderr output."""
        try:
            while self._connected and self.process and self.process.stderr:
                line = await self.process.stderr.readline()
                if not line:
                    break
                msg = line.decode("utf-8", errors="replace").strip()
                if msg:
                    log.debug(f"MCP [{self.config.name}] stderr: {msg}")
        except (asyncio.CancelledError, OSError):
            pass

    async def _notify(self, method: str, params: dict | None = None):
        """Send a JSON-RPC notification (no response expected)."""
        notification = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if params:
            notification["params"] = params

        line = json.dumps(notification, ensure_ascii=False) + "\n"
        self.writer.write(line.encode("utf-8"))
        await self.writer.drain()

    async def _read_loop(self):
        """Read JSON-RPC responses line by line (readline-based)."""
        try:
            while self._connected and self.reader:
                line = await asyncio.wait_for(self.reader.readline(), timeout=120)
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").strip()
                if not text:
                    continue
                try:
                    message = json.loads(text)
                    self._handle_message(message)
                except json.JSONDecodeError:
                    log.debug(f"MCP parse error: {text[:100]}")
        except asyncio.TimeoutError:
            log.debug("MCP read timeout (120s) — end of loop")
        except asyncio.CancelledError:
            pass
        except (OSError, UnicodeDecodeError) as e:
            log.debug(f"MCP read loop ended: {e}")

    def _handle_message(self, message: dict):
        """Handle an incoming JSON-RPC message."""
        # Response?
        if "id" in message:
            req_id = str(message["id"])
            future = self._pending.pop(req_id, None)
            if future and not future.done():
                future.set_result(json.dumps(message, ensure_ascii=False))

        # Error?
        elif "error" in message:
            log.error(f"MCP error: {message['error']}")

        # Notification?
        elif "method" in message:
            log.debug(f"MCP notification: {message['method']}")


class MCPManager:
    """
    Manages multiple MCP servers.
    Aggregates tools from all servers into a single pool.
    """

    def __init__(self):
        self.servers: dict[str, MCPClient] = {}
        self.configs: list[MCPServerConfig] = []

    def add_server(self, config: MCPServerConfig):
        """Add an MCP server."""
        self.configs.append(config)
        self.servers[config.name] = MCPClient(config)

    def remove_server(self, name: str):
        """Remove an MCP server."""
        if name in self.servers:
            client = self.servers.pop(name)
            asyncio.create_task(client.disconnect())
        self.configs = [c for c in self.configs if c.name != name]

    async def connect_all(self):
        """Connect to all servers."""
        for client in self.servers.values():
            try:
                await client.connect()
            except (OSError, ConnectionError, asyncio.TimeoutError) as e:
                log.warning(f"MCP [{client.config.name}] connection failed: {e}")

    async def disconnect_all(self):
        """Disconnect from all servers."""
        for client in self.servers.values():
            await client.disconnect()

    async def list_all_tools(self) -> list[MCPToolDef]:
        """Collect tools from all servers."""
        all_tools = []
        for client in self.servers.values():
            if client._connected:
                tools = await client.list_tools()
                all_tools.extend(tools)
        return all_tools

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """Find and call the tool on the correct server."""
        for client in self.servers.values():
            if not client._connected:
                continue
            tools = await client.list_tools()
            if any(t.name == tool_name for t in tools):
                return await client.call_tool(tool_name, arguments)
        return json.dumps({"error": f"Tool not found (MCP): {tool_name}"})

    async def ping_all(self) -> dict[str, bool]:
        """Ping all servers (only connected ones)."""
        results = {}
        for name, client in self.servers.items():
            if client._connected:
                results[name] = await client.ping()
            else:
                results[name] = False
        return results


# Default MCP manager
mcp_manager = MCPManager()
