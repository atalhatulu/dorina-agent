"""Structured logging — Hermes-inspired.

Log files:
  ~/.dorina/logs/agent.log   — INFO+, all activity
  ~/.dorina/logs/errors.log  — WARNING+, errors and warnings

Features:
  - RotatingFileHandler (5 MB, 3 backups)
  - Session ID thread-local context
  - Secret redaction
  - Rich console output
"""
from __future__ import annotations
import logging
import os
import sys
import threading
from pathlib import Path
from core.constants import DORINA_HOME
from logging.handlers import RotatingFileHandler
from rich.console import Console
from rich.logging import RichHandler
from rich.highlighter import NullHighlighter

# Log console'u markup=False ile ayri tanimla (display.py'den bagimsiz)
_log_console = Console(markup=False, highlight=False, stderr=True)


# ── Log dizini ─────────────────────────────────────────────

LOG_DIR = DORINA_HOME / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ── Session context (thread-local) ─────────────────────────

_session_context = threading.local()

def set_session_context(session_id: str):
    """Set session ID for current thread (appears in all log lines)."""
    _session_context.session_id = session_id

def clear_session_context():
    """Clear session context."""
    _session_context.session_id = None

def _get_session_tag() -> str:
    """Get session tag for log format."""
    sid = getattr(_session_context, "session_id", None)
    return f" [{sid[:12]}]" if sid else ""


# ── Log format ─────────────────────────────────────────────

_LOG_FORMAT = "%(asctime)s %(levelname)s%(session_tag)s %(name)s: %(message)s"
_DATE_FORMAT = "%H:%M:%S"


class SessionInjector(logging.Formatter):
    """Formatter that injects session tag into every record."""
    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "session_tag"):
            record.session_tag = _get_session_tag()
        return super().format(record)


# ── Secret redaction ───────────────────────────────────────

_REDACT_PATTERNS = [
    ("sk-", 20),       # OpenAI-style keys
    ("gsk_", 20),      # Groq keys
    ("ssec-", 20),     # DeepSeek-style
    ("ghp_", 20),      # GitHub PAT
    ("gho_", 20),      # GitHub OAuth
    ("xoxb-", 20),     # Slack bot
    ("xoxp-", 20),     # Slack user
    ("xapp-", 20),     # Slack app
    ("AKIA", 20),      # AWS access key
]

class RedactingFormatter(SessionInjector):
    """Formatter that redacts secrets from log messages."""
    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        for prefix, keep in _REDACT_PATTERNS:
            idx = msg.find(prefix)
            while idx != -1:
                end = idx + keep
                if end < len(msg):
                    msg = msg[:end] + "***" + msg[end:]
                idx = msg.find(prefix, idx + 1)
        return msg


# ── Handler setup ──────────────────────────────────────────

console = Console()

def _quiet_third_party_loggers():
    """Suppress noisy third-party loggers at DEBUG."""
    for name in ("httpx", "httpcore", "openai", "asyncio", "urllib3",
                 "hpack", "grpc", "charset_normalizer", "fsspec"):
        logging.getLogger(name).setLevel(logging.WARNING)


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Setup rotating file + console logging."""
    root = logging.getLogger("dorina")
    root.setLevel(level)

    # Avoid duplicate handlers on repeated calls
    if root.handlers:
        return root

    # ── File handler: agent.log (INFO+) ──
    file_handler = RotatingFileHandler(
        LOG_DIR / "agent.log",
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(RedactingFormatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
    root.addHandler(file_handler)

    # ── File handler: errors.log (WARNING+) ──
    err_handler = RotatingFileHandler(
        LOG_DIR / "errors.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    err_handler.setLevel(logging.WARNING)
    err_handler.setFormatter(RedactingFormatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
    root.addHandler(err_handler)

    # ── Console handler — lazy resolution: uses display.console if available,
    #    otherwise falls back to stderr. After FullScreenREPL starts,
    #    display.console routes through the fullscreen app automatically. ──

    class _DeferredConsoleHandler(RichHandler):
        """RichHandler that resolves the console lazily each emit.

        At startup, stderr is used. After ui.display is imported and
        FullScreenREPL sets _fullscreen_app, output auto-routes through
        the app-aware console without corrupting the fullscreen layout.
        """
        def __init__(self):
            super().__init__(
                console=_log_console,  # temporary, overridden in emit
                markup=False,
                highlighter=NullHighlighter(),
                keywords=[],
                rich_tracebacks=True,
                show_time=False,
                show_path=False,
                level=logging.WARNING,
            )

        def emit(self, record: logging.LogRecord):
            try:
                from ui.display import console as _c
                self.console = _c
            except ImportError:
                self.console = _log_console
            return super().emit(record)

    console_handler = _DeferredConsoleHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(SessionInjector("%(message)s", datefmt=_DATE_FORMAT))
    root.addHandler(console_handler)

    _quiet_third_party_loggers()
    return root


# ── Singleton ──────────────────────────────────────────────

log = setup_logging()
