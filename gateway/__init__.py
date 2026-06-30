"""Gateway — FastAPI REST API for Dorina Agent.

Exposes agent capabilities over HTTP with SSE streaming,
API key authentication, and rate limiting.
"""

from __future__ import annotations

from .main import create_app

__all__ = ["create_app"]
