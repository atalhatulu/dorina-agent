"""HTTP API — FastAPI ile dışarıdan erişim. Chat, araçlar, oturumlar, export."""
from __future__ import annotations
import threading
import uuid
from typing import Optional
from core.logger import log


class GatewayServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 8642):
        self.host = host
        self.port = port
        self._server = None
        self._thread = None
        self._app = None

    def _build_app(self):
        """FastAPI uygulamasını oluştur ve route'ları tanımla."""
        from fastapi import FastAPI, HTTPException, Query, Body
        from fastapi.responses import JSONResponse
        from pydantic import BaseModel

        app = FastAPI(title="Dorina Gateway", version="1.0.0")

        # ── Request/Response modelleri ──────────────────────────
        class ToolListResponse(BaseModel):
            tools: list[str]
            count: int

        class SessionInfo(BaseModel):
            session_id: str
            created: str
            message_count: int

        # ── Root / Health ────────────────────────────────────────
        @app.get("/")
        @app.get("/health")
        def health():
            """Sağlık kontrolü — sunucu çalışıyor mu?"""
            return {
                "name": "Dorina Agent",
                "version": "1.0.0",
                "status": "running",
                "uptime": "active",
            }

        # ── Chat ─────────────────────────────────────────────────
        @app.get("/chat")
        def chat_get(
            query: str = Query("Merhaba", description="Kullanıcı sorgusu"),
        ):
            """GET ile chat (basit sorgular için)."""
            try:
                from orchestrator.agent_loop import loop
                import asyncio
                resp = asyncio.run(loop.process(query))
                return {"response": resp, "session_id": None}
            except ImportError as e:
                return JSONResponse(
                    status_code=503,
                    content={"error": f"Orchestrator modulu yuklenemedi: {e}"},
                )
            except Exception as e:
                return JSONResponse(
                    status_code=500,
                    content={"error": f"Chat hatasi: {e}"},
                )

        @app.post("/chat")
        def chat_post(body: dict = Body(default={"query": "Merhaba"})):
            """POST ile chat — session_id ve stream desteği ile."""
            try:
                from orchestrator.agent_loop import loop
                import asyncio
                query = body.get("query", "Merhaba") if isinstance(body, dict) else "Merhaba"
                session_id = body.get("session_id") if isinstance(body, dict) else None
                resp = asyncio.run(loop.process(query))
                return {"response": resp, "session_id": session_id}
            except ImportError as e:
                raise HTTPException(
                    status_code=503,
                    detail=f"Orchestrator modulu yuklenemedi: {e}",
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Chat hatasi: {e}")

        # ── Tools ────────────────────────────────────────────────
        @app.get("/tools", response_model=ToolListResponse)
        def list_tools():
            """Kullanılabilir araçları listele."""
            try:
                from tools.registry import registry
                tools = [t.name for t in registry.available_tools()]
                return ToolListResponse(tools=tools, count=len(tools))
            except ImportError as e:
                return JSONResponse(
                    status_code=503,
                    content={"tools": [], "count": 0, "error": str(e)},
                )
            except Exception as e:
                return JSONResponse(
                    status_code=500,
                    content={"tools": [], "count": 0, "error": str(e)},
                )

        # ── Sessions ─────────────────────────────────────────────
        @app.get("/sessions", response_model=list[SessionInfo])
        def list_sessions():
            """Aktif oturumları listele."""
            try:
                from session.manager import manager
                raw = manager.list_sessions()
                # Normalize to our model if it's a list of dicts
                sessions = []
                for s in raw:
                    if isinstance(s, dict):
                        sessions.append(SessionInfo(
                            session_id=s.get("session_id", str(uuid.uuid4())),
                            created=s.get("created", "unknown"),
                            message_count=s.get("message_count", 0),
                        ))
                    else:
                        sessions.append(SessionInfo(
                            session_id=str(s),
                            created="unknown",
                            message_count=0,
                        ))
                return sessions
            except ImportError as e:
                return JSONResponse(
                    status_code=503,
                    content={"error": f"Session modulu yuklenemedi: {e}"},
                )
            except Exception as e:
                return JSONResponse(
                    status_code=500,
                    content={"error": f"Session hatasi: {e}"},
                )

        # ── Export ───────────────────────────────────────────────
        @app.post("/export")
        def export_data(request: dict = Body(default={})):
            """Veriyi belirtilen formatta dışa aktar."""
            try:
                from export.formats import export_json, export_markdown, export_html
                fmt = (request or {}).get("format", "json")
                data = (request or {}).get("data", {})
                messages = data.get("messages", [data]) if isinstance(data, dict) else data
                if not isinstance(messages, list):
                    messages = [messages]

                if fmt == "json":
                    result = export_json(messages)
                elif fmt in ("md", "markdown"):
                    result = export_markdown(messages)
                elif fmt == "html":
                    result = export_html(messages)
                else:
                    import json
                    result = json.dumps(data, indent=2, ensure_ascii=False)

                return {
                    "status": "exported",
                    "format": fmt,
                    "data_size": len(str(result)),
                    "path": result,
                }
            except ImportError as e:
                return JSONResponse(
                    status_code=503,
                    content={"error": f"Export modulu yuklenemedi: {e}"},
                )
            except Exception as e:
                return JSONResponse(
                    status_code=500,
                    content={"error": f"Export hatasi: {e}"},
                )

        @app.get("/export/{format_type}")
        def export_get(format_type: str = "json", data: str = Query("{}", description="JSON string of data")):
            """GET ile export (basit kullanım)."""
            try:
                import json
                parsed = json.loads(data) if data else {}
                from export.formats import export_json, export_markdown, export_html
                messages = parsed.get("messages", [parsed]) if isinstance(parsed, dict) else parsed
                if not isinstance(messages, list):
                    messages = [messages]

                if format_type == "json":
                    result = export_json(messages)
                elif format_type in ("md", "markdown"):
                    result = export_markdown(messages)
                elif format_type == "html":
                    result = export_html(messages)
                else:
                    result = json.dumps(parsed, indent=2, ensure_ascii=False)

                return {"status": "exported", "format": format_type, "path": result}
            except Exception as e:
                return JSONResponse(
                    status_code=500,
                    content={"error": f"Export hatasi: {e}"},
                )

        return app

    def start(self):
        """FastAPI sunucuyu arka planda başlat."""
        try:
            import uvicorn

            self._app = self._build_app()

            self._thread = threading.Thread(
                target=uvicorn.run,
                args=(self._app,),
                kwargs={
                    "host": self.host,
                    "port": self.port,
                    "log_level": "info",
                },
                daemon=True,
            )
            self._thread.start()
            log.info(f"Gateway: http://{self.host}:{self.port}")
            return f"Gateway baslatildi: http://{self.host}:{self.port}"

        except ImportError as e:
            return f"Gateway baslatilamadi (bagimli modul eksik): {e}"
        except OSError as e:
            return f"Gateway baslatilamadi (port {self.port} kullanimda): {e}"
        except Exception as e:
            return f"Gateway baslatilamadi: {e}"

    def stop(self):
        """Sunucuyu durdur. (thread'ler daemon oldugu icin uygulama kapaninca
        otomatik durur, ancak clean shutdown icin cagrilabilir.)"""
        log.info("Gateway durduruldu")

    @property
    def is_running(self) -> bool:
        """Sunucu calisiyor mu?"""
        return self._thread is not None and self._thread.is_alive()


gateway = GatewayServer()
