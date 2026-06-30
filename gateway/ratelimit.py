"""Simple in-memory rate limiting for Gateway."""
from __future__ import annotations
import time
from collections import defaultdict
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP sliding window rate limiter."""

    def __init__(self, app, max_requests: int = 60, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        window = self._requests[client_ip]

        # Clean old entries
        cutoff = now - self.window_seconds
        while window and window[0] < cutoff:
            window.pop(0)

        if len(window) >= self.max_requests:
            raise HTTPException(status_code=429, detail="Too many requests. Slow down.")

        window.append(now)
        return await call_next(request)
