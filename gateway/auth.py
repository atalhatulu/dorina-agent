"""API key authentication for the Gateway.

Key management:
- Keys are stored hashed (SHA-256) in ~/.dorina/gateway_keys.json
- Never stored in plaintext
- Admin key generated on first run, printed to stdout
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from pathlib import Path

from core.constants import DORINA_HOME

_KEYS_FILE = DORINA_HOME / "gateway_keys.json"


def _load_keys() -> dict[str, str]:
    """Load hashed keys from disk."""
    if _KEYS_FILE.exists():
        return json.loads(_KEYS_FILE.read_text())
    return {}


def _save_keys(keys: dict[str, str]) -> None:
    """Save hashed keys to disk."""
    _KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _KEYS_FILE.write_text(json.dumps(keys, indent=2))


def _hash_key(key: str) -> str:
    """SHA-256 hash of an API key."""
    return hashlib.sha256(key.encode()).hexdigest()


def generate_key(label: str = "admin") -> str:
    """Generate a new API key, hash it, and store.

    Returns the raw key (shown once at creation).
    """
    raw_key = f"dorina_{secrets.token_hex(24)}"
    key_hash = _hash_key(raw_key)
    keys = _load_keys()
    keys[label] = key_hash
    _save_keys(keys)
    return raw_key


def revoke_key(label: str) -> bool:
    """Revoke an API key by label. Returns True if found/removed."""
    keys = _load_keys()
    if label in keys:
        del keys[label]
        _save_keys(keys)
        return True
    return False


def list_labels() -> list[str]:
    """List all key labels (not the hashes)."""
    return list(_load_keys().keys())


def verify_key(raw_key: str) -> bool:
    """Verify a raw API key against stored hashes.

    Uses constant-time comparison to prevent timing attacks.
    """
    if not raw_key:
        return False
    raw_hash = _hash_key(raw_key)
    for stored_hash in _load_keys().values():
        if hmac.compare_digest(raw_hash, stored_hash):
            return True
    return False


def ensure_admin_key() -> str:
    """Ensure at least one admin key exists. Returns the first admin key or generates one."""
    keys = _load_keys()
    if "admin" in keys:
        return "admin (exists)"
    raw = generate_key("admin")
    return raw
