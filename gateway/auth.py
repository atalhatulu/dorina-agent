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


def generate_token() -> str:
    """Generate a new random token (for setup convenience)."""
    return secrets.token_urlsafe(32)
