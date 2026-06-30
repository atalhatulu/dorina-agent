"""FastAPI application factory and uvicorn entry point.

Usage:
    python -m gateway.main              # start on default port 8080
    python -m gateway.main --port 9090  # custom port
"""

from __future__ import annotations

import argparse
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.constants import VERSION, NAME


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    from .routes import router
    from .auth import ensure_admin_key

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup: ensure admin API key exists
        key_info = ensure_admin_key()
        if key_info and key_info.startswith("dorina_"):
            print(f"  🗝️  Admin API key: {key_info}")
            print(f"  ⚠️  Save this key — it will not be shown again.")
        yield
        # Shutdown: cleanup
        from orchestrator.agent_loop import loop
        await loop.cleanup()

    app = FastAPI(
        title=f"{NAME} API",
        version=VERSION,
        description=f"REST API for {NAME} — self-hosted CLI AI agent",
        lifespan=lifespan,
    )

    # CORS — allow all origins for local development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "detail": str(exc)},
        )

    # Register routes
    app.include_router(router, prefix="/v1")

    @app.get("/")
    async def root():
        return {"service": NAME, "version": VERSION, "docs": "/docs"}

    return app


def main():
    """Entry point: parse args and start uvicorn."""
    parser = argparse.ArgumentParser(description=f"{NAME} Gateway API")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address")
    parser.add_argument("--port", type=int, default=8080, help="Port")
    parser.add_argument("--reload", action="store_true", help="Auto-reload on changes")
    args = parser.parse_args()

    import uvicorn

    print(f"  🚀 {NAME} Gateway v{VERSION}")
    print(f"  📡 http://{args.host}:{args.port}")
    print(f"  📖 http://{args.host}:{args.port}/docs")

    uvicorn.run(
        "gateway.main:create_app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        factory=True,
    )


if __name__ == "__main__":
    main()
