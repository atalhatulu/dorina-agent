"""
LSP tool'ları — lsp_goto_def, lsp_references, lsp_hover, lsp_diagnostics.

Hermes-agent LSP pattern (tool bazlı):
- Her LSP işlemi ayrı bir tool
- @register_tool ile kayıt
- Async çalışır
"""

from __future__ import annotations
import json
from pathlib import Path

from tools.registry import register_tool
from core.logger import log


# ═══════════════════════════════════════════════════════════════
# lsp_goto_def — Tanıma Git
# ═══════════════════════════════════════════════════════════════

@register_tool(
    name="lsp_goto_def",
    description="Kodda bir sembolün tanımlandığı yere git. Dosya, satır ve sütun belirt.",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Dosya yolu (örn. /path/to/file.py)",
            },
            "line": {
                "type": "integer",
                "description": "Satır numarası (0-indexed)",
            },
            "col": {
                "type": "integer",
                "description": "Sütun numarası (0-indexed)",
            },
        },
        "required": ["file_path", "line", "col"],
    },
    toolset="lsp",
)
async def lsp_goto_def(file_path: str, line: int, col: int) -> str:
    """Sembolün tanımlandığı yere git."""
    path = Path(file_path).expanduser()
    if not path.exists():
        return json.dumps({"error": f"Dosya bulunamadi: {file_path}"})

    from lsp.client import lsp
    results = await lsp.goto_definition(str(path), line=line, col=col)
    return json.dumps({"definitions": results}, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════
# lsp_references — Referansları Bul
# ═══════════════════════════════════════════════════════════════

@register_tool(
    name="lsp_references",
    description="Kodda bir sembolün tüm referanslarını bul.",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Dosya yolu",
            },
            "line": {
                "type": "integer",
                "description": "Satır numarası (0-indexed)",
            },
            "col": {
                "type": "integer",
                "description": "Sütun numarası (0-indexed)",
            },
        },
        "required": ["file_path", "line", "col"],
    },
    toolset="lsp",
)
async def lsp_references(file_path: str, line: int, col: int) -> str:
    """Sembolün referanslarını bul."""
    path = Path(file_path).expanduser()
    if not path.exists():
        return json.dumps({"error": f"Dosya bulunamadi: {file_path}"})

    from lsp.client import lsp
    results = await lsp.references(str(path), line=line, col=col)
    return json.dumps({"references": results}, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════
# lsp_hover — Hover Bilgisi
# ═══════════════════════════════════════════════════════════════

@register_tool(
    name="lsp_hover",
    description="Kodda bir noktanın hover bilgisini göster (tip, dokümantasyon).",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Dosya yolu",
            },
            "line": {
                "type": "integer",
                "description": "Satır numarası (0-indexed)",
            },
            "col": {
                "type": "integer",
                "description": "Sütun numarası (0-indexed)",
            },
        },
        "required": ["file_path", "line", "col"],
    },
    toolset="lsp",
)
async def lsp_hover(file_path: str, line: int, col: int) -> str:
    """Hover bilgisini göster."""
    path = Path(file_path).expanduser()
    if not path.exists():
        return json.dumps({"error": f"Dosya bulunamadi: {file_path}"})

    from lsp.client import lsp
    result = await lsp.hover(str(path), line=line, col=col)
    if result:
        return json.dumps({"hover": result}, ensure_ascii=False)
    return json.dumps({"hover": None, "message": "Hover bilgisi bulunamadi"})


# ═══════════════════════════════════════════════════════════════
# lsp_diagnostics — Diagnostik
# ═══════════════════════════════════════════════════════════════

@register_tool(
    name="lsp_diagnostics",
    description="Kod dosyasındaki hata/uyarıları LSP ile kontrol et.",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Dosya yolu",
            },
        },
        "required": ["file_path"],
    },
    toolset="lsp",
)
async def lsp_diagnostics(file_path: str) -> str:
    """Dosyadaki diagnostikleri al."""
    path = Path(file_path).expanduser()
    if not path.exists():
        return json.dumps({"error": f"Dosya bulunamadi: {file_path}"})

    from lsp.client import lsp
    results = await lsp.diagnostics(str(path))
    if results:
        return json.dumps({"diagnostics": results, "count": len(results)}, ensure_ascii=False)
    return json.dumps({"diagnostics": [], "message": "Hata/uyari bulunamadi"})


# ═══════════════════════════════════════════════════════════════
# lsp_completion — Kod Tamamlama (opsiyonel)
# ═══════════════════════════════════════════════════════════════

@register_tool(
    name="lsp_completion",
    description="Kod tamamlama önerileri al.",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Dosya yolu",
            },
            "line": {
                "type": "integer",
                "description": "Satır numarası (0-indexed)",
            },
            "col": {
                "type": "integer",
                "description": "Sütun numarası (0-indexed)",
            },
        },
        "required": ["file_path", "line", "col"],
    },
    toolset="lsp",
)
async def lsp_completion(file_path: str, line: int, col: int) -> str:
    """Kod tamamlama önerileri."""
    path = Path(file_path).expanduser()
    if not path.exists():
        return json.dumps({"error": f"Dosya bulunamadi: {file_path}"})

    from lsp.client import lsp
    results = await lsp.completion(str(path), line=line, col=col)
    return json.dumps({"completions": results, "count": len(results)}, ensure_ascii=False)
