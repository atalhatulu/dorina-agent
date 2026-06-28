"""
LSP Client — Pyright/Pylsp LSP istemcisi.

Hermes-agent LSP pattern:
- JSON-RPC over stdio ile LSP server iletişimi
- Async/sync method'lar
- Otomatik server lifecycle yönetimi
- pyright (hızlı) + pylsp (pylint-ruff) destekleri
"""

from __future__ import annotations
import asyncio
import json
import os
import subprocess
from pathlib import Path
from typing import Optional, Any
from core.logger import log

# ── JSON-RPC helpers ──────────────────────────────────────────

_REQUEST_ID = 0


def _make_request(method: str, params: dict = None) -> str:
    global _REQUEST_ID
    _REQUEST_ID += 1
    body = json.dumps({
        "jsonrpc": "2.0",
        "id": _REQUEST_ID,
        "method": method,
        "params": params or {},
    })
    return f"Content-Length: {len(body)}\r\n\r\n{body}"


def _make_notification(method: str, params: dict = None) -> str:
    body = json.dumps({
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {},
    })
    return f"Content-Length: {len(body)}\r\n\r\n{body}"


def _parse_response(data: str) -> list[dict]:
    """LSP yanıtlarını parse et (birden çok olabilir)."""
    results = []
    while data:
        header_end = data.find("\r\n\r\n")
        if header_end == -1:
            break
        header = data[:header_end]
        content_start = header_end + 4
        length = 0
        for h in header.split("\r\n"):
            if h.lower().startswith("content-length:"):
                length = int(h.split(":")[1].strip())
                break
        if length == 0 or len(data) < content_start + length:
            break
        body = data[content_start:content_start + length]
        try:
            results.append(json.loads(body))
        except json.JSONDecodeError:
            pass
        data = data[content_start + length:]
    return results


# ═══════════════════════════════════════════════════════════════
# LspClient — Ana LSP istemcisi
# ═══════════════════════════════════════════════════════════════

LSP_SERVERS = {
    "pyright": {
        "cmd": ["pyright-langserver", "--stdio"],
        "args": [],
    },
    "pylsp": {
        "cmd": ["pylsp"],
        "args": [],
    },
}


class LspClient:
    """
    Pyright/Pylsp LSP istemcisi.
    JSON-RPC over stdio ile iletişim.
    """

    def __init__(self, server_type: str = "pyright", workspace_root: str = "."):
        self.server_type = server_type
        self.workspace_root = Path(workspace_root).resolve()
        self._process: Optional[subprocess.Popen] = None
        self._buffer = ""
        self._lock = asyncio.Lock()
        self._initialized = False
        self._pending_requests: dict[int, asyncio.Future] = {}
        self._reader_task: Optional[asyncio.Task] = None
        self._capabilities: dict = {}

    @property
    def available(self) -> bool:
        """LSP sunucusu mevcut mu (kurulu mu?)"""
        server = LSP_SERVERS.get(self.server_type)
        if not server:
            return False
        try:
            subprocess.run(
                server["cmd"] + ["--version"],
                capture_output=True, timeout=5
            )
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    async def start(self) -> bool:
        """LSP server'ı başlat."""
        if self._initialized:
            return True

        server = LSP_SERVERS.get(self.server_type)
        if not server:
            log.error(f"Bilinmeyen LSP server: {self.server_type}")
            return False

        try:
            self._process = subprocess.Popen(
                server["cmd"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(self.workspace_root),
            )

            # Reader task
            loop = asyncio.get_event_loop()
            self._reader_task = loop.create_task(self._reader_loop())

            # Initialize
            init_params = {
                "processId": os.getpid(),
                "rootUri": self.workspace_root.as_uri(),
                "rootPath": str(self.workspace_root),
                "capabilities": {
                    "textDocument": {
                        "completion": {"dynamicRegistration": True},
                        "hover": {"dynamicRegistration": True},
                        "definition": {"dynamicRegistration": True},
                        "references": {"dynamicRegistration": True},
                        "diagnostics": {"dynamicRegistration": True},
                    },
                    "workspace": {
                        "didChangeConfiguration": {},
                    },
                },
                "initializationOptions": None,
            }

            req_id = _REQUEST_ID
            self._pending_requests[req_id] = loop.create_future()
            self._write(_make_request("initialize", init_params))

            # Wait for response
            try:
                result = await asyncio.wait_for(self._pending_requests[req_id], timeout=10)
                self._capabilities = result.get("capabilities", {})
            except asyncio.TimeoutError:
                log.error("LSP initialize timeout")
                await self.stop()
                return False
            finally:
                self._pending_requests.pop(req_id, None)

            # Initialized notification
            self._write(_make_notification("initialized"))

            self._initialized = True
            log.info(f"LSP {self.server_type} baslatildi: {self.workspace_root}")
            return True

        except Exception as e:
            log.error(f"LSP baslatilamadi: {e}")
            return False

    async def stop(self):
        """LSP server'ı durdur."""
        if self._initialized:
            self._write(_make_notification("exit"))
            self._initialized = False

        if self._reader_task:
            self._reader_task.cancel()
            self._reader_task = None

        if self._process:
            try:
                self._process.stdin.close()
                self._process.wait(timeout=5)
            except Exception:
                self._process.kill()
            self._process = None

    def _write(self, data: str):
        """LSP server'a veri yaz."""
        if self._process and self._process.stdin:
            self._process.stdin.write(data.encode())
            self._process.stdin.flush()

    async def _reader_loop(self):
        """LSP çıktısını oku ve parse et."""
        loop = asyncio.get_event_loop()

        while self._process and self._process.stdout:
            try:
                data = await loop.run_in_executor(
                    None, self._process.stdout.readline
                )
                if not data:
                    break
                self._buffer += data.decode(errors="replace")

                # Parse complete responses
                responses = _parse_response(self._buffer)
                if responses:
                    self._buffer = ""
                    for resp in responses:
                        await self._handle_response(resp)

            except Exception as e:
                log.error(f"LSP reader hatasi: {e}")
                break

    async def _handle_response(self, resp: dict):
        """LSP yanıtını işle."""
        # Notification (method field, no id)
        if "method" in resp:
            return

        # Response
        req_id = resp.get("id")
        if req_id is not None and req_id in self._pending_requests:
            future = self._pending_requests[req_id]
            if "result" in resp:
                future.set_result(resp["result"])
            elif "error" in resp:
                future.set_exception(Exception(resp["error"]["message"]))

    async def _request(self, method: str, params: dict = None, timeout: int = 30) -> Any:
        """LSP'ye istek gönder ve yanıt bekle."""
        if not self._initialized:
            started = await self.start()
            if not started:
                return {"error": "LSP server baslatilamadi"}

        loop = asyncio.get_event_loop()
        req_id = _REQUEST_ID
        future = loop.create_future()
        self._pending_requests[req_id] = future
        self._write(_make_request(method, params))

        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            log.error(f"LSP request timeout: {method}")
            return {"error": "timeout"}
        finally:
            self._pending_requests.pop(req_id, None)

    def _text_doc_params(self, file_path: str) -> dict:
        """TextDocumentItem parametrelerini oluştur."""
        path = Path(file_path).resolve()
        return {
            "textDocument": {
                "uri": path.as_uri(),
                "languageId": self._detect_language(path),
                "version": 1,
                "text": path.read_text(errors="replace") if path.exists() else "",
            }
        }

    def _doc_id(self, file_path: str) -> dict:
        """TextDocumentIdentifier oluştur."""
        path = Path(file_path).resolve()
        return {"uri": path.as_uri()}

    @staticmethod
    def _detect_language(path: Path) -> str:
        """Dosya uzantısından dil tespiti."""
        ext = path.suffix.lower()
        lang_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".tsx": "typescriptreact",
            ".jsx": "javascriptreact",
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
            ".cpp": "cpp",
            ".c": "c",
            ".cs": "csharp",
            ".rb": "ruby",
            ".php": "php",
            ".swift": "swift",
            ".kt": "kotlin",
            ".scala": "scala",
            ".html": "html",
            ".css": "css",
            ".json": "json",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".md": "markdown",
            ".sql": "sql",
            ".sh": "shellscript",
            ".bash": "shellscript",
        }
        return lang_map.get(ext, "plaintext")

    # ── LSP Method'ları ────────────────────────────────────────

    async def did_open(self, file_path: str):
        """Dosya açıldı bildirimi."""
        params = self._text_doc_params(file_path)
        self._write(_make_notification("textDocument/didOpen", params))

    async def did_change(self, file_path: str, text: str):
        """Dosya değişti bildirimi."""
        params = {
            "textDocument": self._doc_id(file_path),
            "contentChanges": [{"text": text}],
        }
        self._write(_make_notification("textDocument/didChange", params))

    async def did_close(self, file_path: str):
        """Dosya kapatıldı bildirimi."""
        params = {"textDocument": self._doc_id(file_path)}
        self._write(_make_notification("textDocument/didClose", params))

    async def goto_definition(self, file_path: str, line: int, col: int) -> list[dict]:
        """Tanıma git."""
        params = {
            "textDocument": self._doc_id(file_path),
            "position": {"line": line, "character": col},
        }
        result = await self._request("textDocument/definition", params)
        if isinstance(result, list):
            return [
                {
                    "uri": loc.get("uri", ""),
                    "range": loc.get("range", {}),
                    "file": Path(loc.get("uri", "").replace("file://", "")).name if loc.get("uri") else "",
                    "line": loc.get("range", {}).get("start", {}).get("line", 0),
                }
                for loc in result
            ]
        elif isinstance(result, dict):
            return [{
                "uri": result.get("uri", ""),
                "range": result.get("range", {}),
            }]
        return []

    async def references(self, file_path: str, line: int, col: int) -> list[dict]:
        """Referansları bul."""
        params = {
            "textDocument": self._doc_id(file_path),
            "position": {"line": line, "character": col},
            "context": {"includeDeclaration": True},
        }
        result = await self._request("textDocument/references", params)
        if isinstance(result, list):
            return [
                {
                    "uri": ref.get("uri", ""),
                    "range": ref.get("range", {}),
                    "file": Path(ref.get("uri", "").replace("file://", "")).name if ref.get("uri") else "",
                    "line": ref.get("range", {}).get("start", {}).get("line", 0),
                }
                for ref in result
            ]
        return []

    async def hover(self, file_path: str, line: int, col: int) -> Optional[str]:
        """Hover bilgisi."""
        params = {
            "textDocument": self._doc_id(file_path),
            "position": {"line": line, "character": col},
        }
        result = await self._request("textDocument/hover", params)
        if result and "contents" in result:
            contents = result["contents"]
            if isinstance(contents, dict):
                return contents.get("value", "")
            elif isinstance(contents, list):
                return "\n".join(
                    c.get("value", str(c)) if isinstance(c, dict) else str(c)
                    for c in contents
                )
            return str(contents)
        return None

    async def diagnostics(self, file_path: str) -> list[dict]:
        """Diagnostik bilgilerini al."""
        # Önce dosyayı aç
        await self.did_open(file_path)

        # Diagnostics iste (publishDiagnostics notification'dan gelir)
        params = {"textDocument": self._doc_id(file_path)}
        result = await self._request("textDocument/diagnostic", params)

        if isinstance(result, dict):
            items = result.get("items", [])
            return [
                {
                    "range": d.get("range", {}),
                    "severity": d.get("severity", 0),
                    "message": d.get("message", ""),
                    "source": d.get("source", ""),
                    "code": d.get("code", ""),
                    "line": d.get("range", {}).get("start", {}).get("line", 0),
                    "col": d.get("range", {}).get("start", {}).get("character", 0),
                }
                for d in items
            ]
        return []

    async def completion(self, file_path: str, line: int, col: int) -> list[dict]:
        """Kod tamamlama önerileri."""
        params = {
            "textDocument": self._doc_id(file_path),
            "position": {"line": line, "character": col},
            "context": {"triggerKind": 1},
        }
        result = await self._request("textDocument/completion", params)
        if isinstance(result, dict):
            items = result.get("items", [])
        elif isinstance(result, list):
            items = result
        else:
            return []

        return [
            {
                "label": c.get("label", ""),
                "kind": c.get("kind", 0),
                "detail": c.get("detail", ""),
                "documentation": c.get("documentation", ""),
            }
            for c in items
        ]

    async def document_symbols(self, file_path: str) -> list[dict]:
        """Dosyadaki sembolleri listele."""
        params = {"textDocument": self._doc_id(file_path)}
        result = await self._request("textDocument/documentSymbol", params)
        if isinstance(result, list):
            return [
                {
                    "name": s.get("name", ""),
                    "kind": s.get("kind", 0),
                    "detail": s.get("detail", ""),
                    "range": s.get("range", {}),
                    "selectionRange": s.get("selectionRange", {}),
                }
                for s in result
            ]
        return []


# Singleton
lsp = LspClient(server_type="pyright")
