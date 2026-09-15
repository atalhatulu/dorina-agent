"""
Dashboard auth — optional token-based protection.

Token kaynakları (öncelik sırasıyla):
  1. ~/.dorina/config.yaml → dashboard.token
  2. Environment: DORINA_DASHBOARD_TOKEN

Token tanımlı DEĞİLSE auth kapalıdır (localhost-only bind zaten güvenli).
Token tanımlıysa REST istekleri `X-Dashboard-Token` header'ı, WebSocket
bağlantıları `?token=` query param'ı ister.

Felsefe: kısıtlama değil, kullanıcı isterse aktif olan opsiyonel koruma.
"""
from __future__ import annotations
import os
import hmac
import secrets

_token: str | None = None
_loaded = False


def _load_token() -> str | None:
    """Load token from config or env. Cached after first call."""
    global _token, _loaded
    if _loaded:
        return _token
    # 1. ~/.dorina/config.yaml → dashboard.token
    try:
        from core.config import settings
        tok = getattr(settings, "dashboard", None)
        if tok:
            tok = getattr(tok, "token", None)
        if tok and isinstance(tok, str) and tok.strip():
            _token = tok.strip()
    except (ImportError, AttributeError):
        pass
    # 2. Environment
    if not _token:
        _token = os.environ.get("DORINA_DASHBOARD_TOKEN", "").strip() or None
    _loaded = True
    return _token


def reset_token_cache() -> None:
    """Reset cached token state."""
    global _token, _loaded
    _token = None
    _loaded = False


def reload_token() -> str | None:
    """Reset cached token and reload."""
    reset_token_cache()
    return _load_token()


def is_auth_enabled() -> bool:
    return bool(_load_token())


def get_token() -> str | None:
    return _load_token()


def verify_token(candidate: str | None) -> bool:
    """Constant-time comparison to avoid timing attacks."""
    tok = _load_token()
    if not tok:
        return True  # auth kapalı → herkes geçer
    if not candidate:
        return False
    return hmac.compare_digest(candidate, tok)


def is_origin_allowed(origin: str | None, host: str | None = None) -> bool:
    """Check whether a WebSocket or HTTP request Origin is permitted.

    Non-browser clients (no Origin header) are allowed.
    If an Origin header is present, it must match configured allowed_origins
    or the request Host header.
    """
    if not origin:
        return True

    allowed: list[str] = []
    try:
        from core.config import settings
        dash = getattr(settings, "dashboard", None)
        if dash and hasattr(dash, "allowed_origins"):
            allowed = [o.rstrip("/") for o in dash.allowed_origins if o]
    except Exception:
        pass

    if not allowed:
        allowed = [
            "http://localhost:5792",
            "http://127.0.0.1:5792",
            "http://localhost",
            "http://127.0.0.1",
        ]

    origin_clean = origin.rstrip("/")
    if origin_clean in allowed:
        return True

    if host:
        from urllib.parse import urlparse
        parsed = urlparse(origin_clean)
        host_clean = host.strip().lower()
        if parsed.netloc.lower() == host_clean:
            return True

    return False


def generate_token() -> str:
    """Generate a new random token (for setup convenience)."""
    return secrets.token_urlsafe(32)
