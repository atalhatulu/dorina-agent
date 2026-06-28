"""
Dorina Agent — LSP (Language Server Protocol) modülü.

Hermes-agent LSP pattern:
- Pyright/Pylsp LSP client ile kod analizi
- lsp_goto_def, lsp_references, lsp_hover, lsp_diagnostics
- Dosya açıkken arka planda LSP server çalıştırma

Kullanım:
    from lsp.client import LspClient, lsp
    diag = await lsp.diagnostics("/path/to/file.py")
    defs = await lsp.goto_definition("/path/to/file.py", line=10, col=5)
"""

from __future__ import annotations
from lsp.client import LspClient, lsp

__all__ = ["LspClient", "lsp"]
