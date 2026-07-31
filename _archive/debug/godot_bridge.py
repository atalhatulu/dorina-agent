#!/usr/bin/env python3
"""
Dorina Godot Bridge — HTTP API for Godot AI Assistant plugin.

Starts a lightweight HTTP server on port 8333.
Godot plugin sends prompts here instead of calling Ollama directly.

Usage:
    python godot_bridge.py              # default port 8333
    python godot_bridge.py --port 9000  # custom port
"""
from __future__ import annotations
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from aiohttp import web

# Dorina ortamını hazırla
sys.path.insert(0, str(Path(__file__).resolve().parent))
from core.bootstrap import suppress_noisy_logs, ensure_project_root, init_api_keys
suppress_noisy_logs()
ensure_project_root()
init_api_keys()

from core.logger import log
from core.constants import NAME
from orchestrator.experimental_loop import loop_v2 as loop


async def handle_ask(request):
    """POST /ask — accept {prompt, system_prompt?}, return {response, error?}."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    prompt = body.get("prompt", "")
    if not prompt:
        return web.json_response({"error": "prompt is required"}, status=400)

    # Godot proje dizinini ayarla (varsa)
    godot_project = body.get("project_path", "")
    if godot_project and os.path.isdir(godot_project):
        os.chdir(godot_project)

    try:
        response = await loop.process(prompt)

        # response string ise düz döndür, yoksa metne çevir
        if isinstance(response, str):
            text = response
        elif hasattr(response, "content"):
            text = response.content
        else:
            text = str(response)

        return web.json_response({"response": text})

    except Exception as e:
        log.error(f"GodotBridge error: {e}")
        return web.json_response({"error": str(e)}, status=500)


async def handle_health(request):
    """GET /health — bridge çalışıyor mu kontrolü."""
    return web.json_response({
        "status": "ok",
        "agent": NAME,
        "port": request.app.get("port", 8333),
    })


async def create_app(port: int = 8333):
    """aiohttp web uygulamasını oluştur."""
    app = web.Application()
    app["port"] = port
    app.router.add_post("/ask", handle_ask)
    app.router.add_get("/health", handle_health)

    log.info(f"🌉 Godot Bridge listening on http://127.0.0.1:{port}")
    log.info(f"   Godot plugin'i http://127.0.0.1:{port}/ask adresine POST yapacak")
    log.info(f"   Sağlık kontrolü: http://127.0.0.1:{port}/health")
    return app


def main():
    parser = argparse.ArgumentParser(description="Dorina Godot Bridge")
    parser.add_argument("--port", type=int, default=8333, help="Port (default: 8333)")
    args = parser.parse_args()

    # Windows'ta event loop policy
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    app = asyncio.run(create_app(args.port))
    web.run_app(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
