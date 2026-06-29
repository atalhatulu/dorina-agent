#!/usr/bin/env python3
"""
Dorina Agent — Self-hosted CLI AI agent.

Kullanım:
    python main.py                    # Interaktif mod
    python main.py -q "soru"         # Tek sorgu
    python main.py --new              # Yeni oturum
"""

from __future__ import annotations
import argparse
import asyncio
import json
import sys
from pathlib import Path
from core.constants import DORINA_HOME

# Add project root to PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Suppress litellm/OpenAI noisy logs globally before any module imports litellm
import os
os.environ.setdefault("LITELLM_LOG", "WARNING")
os.environ.setdefault("OPENAI_LOG_LEVEL", "WARNING")
os.environ.setdefault("LITELLM_SUPPRESS_DEBUG_INFO", "1")
os.environ.setdefault("LITELLM_VERBOSE", "False")
os.environ.setdefault("LITELLM_DEBUG", "False")
os.environ.setdefault("LITELLM_DISABLE_LOGS", "True")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

# Suppress HuggingFace Hub progress bar warning (harmless but ugly)
import warnings
warnings.filterwarnings("ignore", message="Cannot enable progress bars")

from core.logger import log, console
from core.config import settings
from core.constants import VERSION, NAME
from core.version_manager import get_version_manager
from soul.personality import soul
from soul.preferences import prefs
from ui.repl import create_session, get_input
from ui.display import (
    print_markdown, print_panel, print_success, print_info,
    print_error, print_divider, print_user, print_assistant, print_table,
)
import ui.display as display
from ui.status_bar import status
from orchestrator.agent_loop import loop
from tools.registry import registry
from tools.builtin import basic  # noqa: F401
from tools.builtin import advanced  # noqa: F401
from tools.builtin import modules  # noqa: F401
from tools.builtin import terminal_utils  # noqa: F401
from tools.builtin import terminal_pro  # noqa: F401
from tools.builtin import file_analytics  # noqa: F401
from tools.builtin import workflow_tool  # noqa: F401
from tools.builtin import git_tools  # noqa: F401
from tools.builtin import clarify_tool  # noqa: F401
from tools.builtin import cron_tools  # noqa: F401
from tools.builtin import memory_tools  # noqa: F401
from tools.builtin import bg_task_tool  # noqa: F401
from tools.builtin import graphify_tools  # noqa: F401
from mail import tools as mail_tools  # noqa: F401
from lsp import tools as lsp_tools  # noqa: F401
from evolution import tools as evolution_tools  # noqa: F401
from history import tools as history_tools  # noqa: F401
from agents import task_tools  # noqa: F401
from orchestrator import plan_tools  # noqa: F401
from session.manager import manager
from memory.semantic import SemanticMemory
from providers.keys import keys  # noqa: F401
from providers.keys import PROVIDERS as _PROV
import os as _os


def ensure_package(package: str, pip_name: str | None = None, extra_check: callable | None = None):
    """Eksik paketi otomatik kur. ChromaDB özel kontrolü ile."""
    import importlib, subprocess, sys, os
    name = pip_name or package

    # ChromaDB: chromadb-client (http-only) kuruluysa kaldır, full chromadb kur
    if package == "chromadb":
        try:
            importlib.import_module("chromadb")
            # Check if it's the http-only client version
            try:
                import chromadb
                # Try PersistentClient — fails on chromadb-client
                getattr(chromadb, "PersistentClient", None)
            except Exception:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "chromadb"],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except ImportError:
            try:
                importlib.import_module("chromadb_client")
                subprocess.check_call([sys.executable, "-m", "pip", "uninstall", "-y", "chromadb-client"],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except ImportError:
                pass
            subprocess.check_call([sys.executable, "-m", "pip", "install", "chromadb"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return

    try:
        importlib.import_module(package)
        if extra_check:
            extra_check()
    except (ImportError, Exception):
        subprocess.check_call([sys.executable, "-m", "pip", "install", name],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _init_api_keys():
    """Load API keys from KeyManager into environment."""
    for _p_name, _p_info in _PROV.items():
        _env_name = _p_info.get("env", "")
        if not _env_name:
            continue  # skip providers without env var (e.g. ollama)
        _p_key = keys.get_key(_p_name)
        if _p_key:
            _os.environ[_env_name] = _p_key


_init_api_keys()
from memory.procedural import ProceduralMemory
from memory.episodic import EpisodicMemory

from knowledge.rag_engine import rag
from skills.manager import skills
from security.auth import auth
from security.sandbox import sandbox
from core.event_bus import bus

# ── Versiyon bilgisi (startup'ta da gösterilir) ──
_vm = get_version_manager()
print(f"  [dorina-agent] v{_vm.current} | Versiyon Yöneticisi: {_vm._file.name}")


class DorinaApp:
    """Ana uygulama."""

    def __init__(self):
        self.repl = create_session()
        self.procedural = ProceduralMemory()
        self.running = False

    async def startup(self):
        """Başlangıç: ~/.dorina/ dizinleri + eksik paketler + servisler + banner."""
        import os
        
        # Ensure ~/.dorina/ directory structure
        from core.constants import ensure_dorina_home
        ensure_dorina_home()
        
        # Auto-install critical packages
        ensure_package("chromadb")

        import subprocess
        subprocess.run(["cmd", "/c", "cls"] if sys.platform == "win32" else ["clear"], check=False)

        from ui.display import console
        console.print("\n  [dim]Hazırlanıyor... (Bellek ve Araçlar indeksleniyor)[/dim]")

        # Eager initialization at startup
        await rag.initialize()
        from tools.selector import selector as _sel
        await _sel.initialize()

        console.print("  [dim]Hazır.[/dim]")

        # Try Docker sandbox
        sandbox.initialize()

        # MCP (opsiyonel)
        mcp_status = "hazir"
        if settings.tools.mcp_enabled:
            try:
                from tools.mcp.client import mcp_manager
                mcp_status = "hazir (sunucu yok)"
            except Exception:
                mcp_status = "yok"

        # ~/.dorina/config.yaml'dan model ayarini oku
        _cfg_path = DORINA_HOME / "config.yaml"
        if _cfg_path.exists():
            try:
                import yaml as _yaml
                _cfg = _yaml.safe_load(_cfg_path.read_text())
                if _cfg and "model" in _cfg:
                    if "provider" in _cfg["model"]:
                        settings.model.provider = _cfg["model"]["provider"]
                    if "default" in _cfg["model"]:
                        settings.model.default = _cfg["model"]["default"]
            except Exception:
                pass

        # Start session
        model_info = f"{settings.model.provider}/{settings.model.default.split('/')[-1]}"
        session_id = manager.create(model=model_info)
        # Set session context for logging
        from core.logger import set_session_context
        set_session_context(session_id)
        status.model = settings.model.default
        status.provider = settings.model.provider

        # First-run setup check
        from ui.setup_wizard import needs_setup
        if needs_setup():
            from ui.setup_wizard import run_setup_wizard
            await run_setup_wizard()

        # User profile check
        from ui.setup_wizard import has_user_profile, run_user_profile_wizard
        if not has_user_profile():
            run_user_profile_wizard()

        # === BANNER ===
        import os as _os
        import subprocess as _sp
        _sp.run(["cmd", "/c", "cls"] if sys.platform == "win32" else ["clear"], check=False)
        
        tools_available = registry.available_tools()
        tools_all = [(t.name, t.description[:25]) for t in registry.list() 
                     if t.check_fn is None or t.check_fn()]
        skill_list = [(s["name"], s.get("description", "")[:25]) for s in skills.list_skills()]
        
        from ui.banner import print_startup_banner
        from ui.display import console
        
        print_startup_banner(
            model_info=model_info,
            session_id=session_id,
            tools_available=tools_available,
            tools_all=tools_all,
            skills=skill_list,
            api_keys=auth.list_providers(),
        )
        
        console.print(f"  [dim]17 referans proje · 33 modul · 56 tool[/dim]")
        console.print(f"  [dim]/help yaz veya / ile baslayip Tab'a bas[/dim]\n")

        # ── Versiyon bilgisi ──
        _vm = get_version_manager()
        console.print(f"  [bold green]🐍 {NAME} v{_vm.current}[/bold green] — [dim]Versiyon Yöneticisi: hazır[/dim]")

    def _on_tool_called(self, event: str, name: str, arguments: dict, **kw):
        status.add_tool_call()

    def _on_tool_completed(self, event: str, name: str, result: str, **kw):
        pass  # İleride log'lama için

    async def run_interactive(self):
        """Interaktif REPL döngüsü."""
        from ui.repl import get_input as repl_input
        self.running = True
        
        while self.running:
            try:
                # Check background tasks notifications
                from bg_tools.task_manager import task_manager
                notifs = task_manager.pop_notifications()
                if notifs:
                    from ui.display import print_info
                    for notif in notifs:
                        print_info(notif)
                
                # ─── > prompt (Live kapalı, terminal özgür) ───
                from ui.status_bar import status as _sb_status
                _sb_status.pause()
                user_input = await repl_input()

                if not user_input:
                    continue

                # Command processing
                if user_input.startswith("/"):
                    _sb_status.resume()
                    await self._handle_command(user_input)
                    _sb_status.pause()
                    continue

                # ─── Resume Live for AI work ───
                _sb_status.resume()
                display.print_divider()

                # Disable terminal echo while AI is working
                import termios
                import sys
                fd = sys.stdin.fileno()
                old_attr = termios.tcgetattr(fd)
                try:
                    new_attr = termios.tcgetattr(fd)
                    new_attr[3] = new_attr[3] & ~termios.ECHO & ~termios.ICANON
                    termios.tcsetattr(fd, termios.TCSANOW, new_attr)

                    gen_task = asyncio.create_task(loop.process(user_input))
                    try:
                        response = await gen_task
                    except (KeyboardInterrupt, asyncio.CancelledError):
                        gen_task.cancel()
                        from ui.display import console as _ui_console, flush_stream
                        flush_stream()
                        _ui_console.print("\n[dim]İptal edildi. (Ctrl+C)[/dim]")
                        # Context'e kaydet (Autosave ile dosyaya da yazilacak)
                        loop.context.messages.append({"role": "system", "content": "Kullanıcı işlemi (Ctrl+C) ile yarıda kesti. Son çıktı veya komut işlemi yarım kalmış olabilir."})
                        # Let litellm finish cancelling
                        await asyncio.sleep(0.1)
                        continue
                finally:
                    # Restore and flush any keys typed during generation
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_attr)
                    termios.tcflush(fd, termios.TCIFLUSH)

                # Flush stream buffer (remaining chunks not yet displayed)
                from ui.display import flush_stream as _fs
                _fs()

                # ─── Pause Live — input beklerken terminal özgür ───
                _sb_status.pause()

                # ─── Dorina response (skip if already streamed) ───
                if not getattr(loop, '_streamed_this_turn', False):
                    display.print_assistant(response)

                # ─── Spacing (shown at status bar loop start) ───
                display.print_divider()

                # Otomatik kaydet
                if settings.session.auto_save:
                    manager.save(
                        loop.context.get_messages(),
                        summary=response[:200],
                    )
            except KeyboardInterrupt:
                print("\n")
                continue
            except EOFError:
                break
            except Exception as e:
                print_error(f"Hata: {e}")
                log.error(f"Beklenmeyen hata", exc_info=True)

    async def run_single_query(self, query: str):
        """Tek sorgu modu."""
        response = await loop.process(query)
        console.print(response)

    async def _handle_command(self, command: str):
        """Slash komutlarını işle."""
        cmd = command.lower().strip()
        
        if cmd in ("/exit", "/quit", "/q"):
            print_info("Görüşürüz!")
            self.running = False

        elif cmd == "/new" or cmd.startswith("/new "):
            if not hasattr(self, 'godmode'):
                self.godmode = False
            loop.reset()
            title = ""
            if len(command) > 5:
                title = command[5:].strip().strip("\"'")
            session_id = manager.create(title=title, model=f"{settings.model.provider}/{settings.model.default.split('/')[-1]}")
            print_success(f"Yeni oturum: {title or session_id}")
        elif cmd == "/godmode":
            from core import constants
            import soul.personality as _sp
            if not hasattr(settings.model, "godmode"):
                settings.model.godmode = False
            settings.model.godmode = not settings.model.godmode
            godmode_active = settings.model.godmode
            _sp.GODMODE = godmode_active

            import os
            from ui.repl import set_style
            from ui.display import console as _gm_console

            if godmode_active:
                os.system("clear")
                set_style(True)
                settings.security.block_destructive_commands = False
                constants.MAX_TURNS = 200
                constants.MAX_TOOL_CALLS_PER_TURN = 999
                banner = (
                    "╔══════════════════════════════╗\n"
                    "║      ⚡ GOD MODE AKTIF ⚡     ║\n"
                    "║   Tüm kısıtlamalar kalktı   ║\n"
                    "╚══════════════════════════════╝"
                )
                _gm_console.print(banner, style="bold red")
                from prompt_toolkit import PromptSession
                session = PromptSession()
                pwd = await session.prompt_async("Sudo şifreniz (RAM'de tutulacak, boş geçmek için Enter): ", is_password=True)
                if pwd:
                    _sp.SUDO_PASSWORD = pwd
            else:
                _sp.SUDO_PASSWORD = None
                os.system("clear")
                set_style(False)
                settings.security.block_destructive_commands = True
                constants.MAX_TURNS = 50
                constants.MAX_TOOL_CALLS_PER_TURN = 30
                print_success("God Mode KAPALI")
            return True
        elif cmd == "/audit":
            from ui.repl import set_style
            import soul.personality as _sp
            import os
            from ui.display import console
            _sp.AUDIT_MODE = not _sp.AUDIT_MODE
            set_style("audit" if _sp.AUDIT_MODE else False)
            os.system("clear")
            if _sp.AUDIT_MODE:
                banner = (
                    "╔══════════════════════════════╗\n"
                    "║      🔍 AUDIT MOD ACIK       ║\n"
                    "║    Tüm kodlar mercek altında ║\n"
                    "╚══════════════════════════════╝"
                )
                console.print(banner, style="bold #E06C75")
                print_info("Örnek komutlar:\n  > self_check ile bu projeyi detaylıca tara\n  > lsp_diagnostics <dosya> ile hataları listele\n  > diff_history ile son değişiklikleri incele")
            else:
                print_success("Audit Mod KAPALI")
            return True
        elif cmd.startswith("/model"):
            parts = command.split()
            if len(parts) > 1:
                model_str = parts[1].strip()
                if "/" in model_str:
                    provider, model_name = model_str.split("/", 1)
                    from core.config import settings
                    settings.model.provider = provider
                    settings.model.default = model_str
                    settings.save()
                    from ui.status_bar import status
                    status.model = model_str
                    print_success(f"Model değiştirildi: {model_str}")
                else:
                    print_error("Hatalı format. Örnek: /model openai/gpt-4o")
            else:
                from ui.setup_wizard import run_setup_wizard
                await run_setup_wizard()
                print_success("Model güncellendi")

        elif cmd.startswith("/export "):
            fmt = cmd[8:].strip().lower()
            from export.formats import export_json, export_markdown, export_html
            msgs = loop.context.get_messages()
            if fmt == "json":
                path = export_json(msgs)
            elif fmt == "md":
                path = export_markdown(msgs)
            elif fmt == "html":
                path = export_html(msgs)
            else:
                print_error(f"Bilinmeyen format: {fmt} (json/md/html)")
                return
            print_success(f"Dışa aktarıldı: {path}")

        elif cmd.startswith("/save "):
            title = cmd[6:].strip()
            manager.save(loop.context.get_messages(), summary=title, title=title)
            if manager.current_id:
                manager.rename(manager.current_id, title)
            print_success(f"Kaydedildi: {title}")

        elif cmd.startswith("/load "):
            sid = cmd[6:].strip()
            session = manager.load(sid)
            if not session:
                # Try as row number
                all_sessions = manager.list_sessions(limit=100)
                try:
                    idx = int(sid) - 1
                    if 0 <= idx < len(all_sessions):
                        sid = all_sessions[idx]["id"]
                        session = manager.load(sid)
                except ValueError:
                    pass
                # Try prefix match
                if not session:
                    for s in all_sessions:
                        if s["id"].startswith(sid):
                            session = manager.load(s["id"])
                            if session:
                                sid = s["id"]
                                break
            if session:
                loop.context.clear()
                # Preserve full message dicts (content, tool_calls, tool_call_id, name, etc.)
                msgs = session.get("messages", [])
                loop.context.messages = msgs
                title = session.get("title", sid)
                # ─── Display entire conversation history ───
                console.print(f"\n[#D4622A]# Session: {title}[/#D4622A]")
                console.print(f"  [dim]ID: {sid} · {len(msgs)} message(s)[/dim]\n")
                for m in msgs:
                    role = m.get("role", "")
                    content = m.get("content", "") or ""
                    if role == "user":
                        console.print(f"  [dim]>[/dim] {content}")
                    elif role == "assistant":
                        tc = m.get("tool_calls")
                        if tc:
                            tool_names = [t["function"]["name"] for t in tc]
                            console.print(f"  [#D4622A]# Dorina #[/#D4622A] [dim]🛠️  {', '.join(tool_names)}[/dim]")
                        elif content.strip():
                            console.print(f"  [#D4622A]# Dorina #[/#D4622A]")
                            for line in content.split("\n"):
                                if line.strip():
                                    console.print(f"    {line}")
                                else:
                                    console.print()
                    elif role == "tool":
                        tc_id = m.get("tool_call_id", "")[:12]
                        name = m.get("name", "?")
                        summary = content.strip()[:80].replace("\n", " ")
                        console.print(f"    [dim]🔧 [{name}] {summary}[/dim]")
                console.print(f"\n  [#6bb05d]✓[/#6bb05d] Session loaded. Agent ready — type your message to continue.")
            else:
                print_error(f"Session not found: {sid}")

        elif cmd == "/sessions":
            sessions = manager.list_sessions()
            console.print("\n[bold #D4622A]# Session List[/bold #D4622A]")
            console.print(f"  [dim]{'#':<4} {'Title':<28} {'Preview':<33} {'Msgs':<5} {'Last Active':<12} ID[/dim]")
            console.print(f"  [dim]{'─'*4:<4} {'─'*28:<28} {'─'*33:<33} {'─'*5:<5} {'─'*12:<12} ────────────[/dim]")
            for i, s in enumerate(sessions, 1):
                title = s["title"][:26] + ".." if len(s["title"]) > 26 else s["title"]
                preview = s.get("summary", "")[:31] + "..." if len(s.get("summary", "")) > 31 else s.get("summary", "")
                msgs = s.get("message_count", 0)
                last_active_raw = s.get("updated_at", s.get("created_at", ""))
                if last_active_raw and len(last_active_raw) >= 16:
                    # Parse ISO format: 2026-06-25T21:40:00 → 25-06-2026-2140
                    dt = last_active_raw[:16].replace("T", "-").replace(":", "")
                    parts = dt.split("-")
                    if len(parts) >= 4:
                        last_active = f"{parts[2]}-{parts[1]}-{parts[0]}-{parts[3]}"
                    else:
                        last_active = last_active_raw[:10]
                else:
                    last_active = last_active_raw[:10] if last_active_raw else ""
                sid = s["id"][:12]
                console.print(f"  {i:<4} {title:<28} {preview:<33} {msgs:<5} {last_active:<12} {sid}")

        elif cmd.startswith("/remove "):
            sid = cmd[8:].strip()
            if sid:
                session = manager.load(sid)
                if not session:
                    # Try prefix match
                    all_sessions = manager.list_sessions(limit=100)
                    # Try as row number (#)
                    try:
                        idx = int(sid) - 1
                        if 0 <= idx < len(all_sessions):
                            sid = all_sessions[idx]["id"]
                            session = manager.load(sid)
                    except ValueError:
                        pass
                    # Try prefix match
                    if not session:
                        for s in all_sessions:
                            if s["id"].startswith(sid):
                                session = manager.load(s["id"])
                                if session:
                                    sid = s["id"]
                                    break
                if session:
                    manager.delete(sid)
                    print_success(f"Silindi: {sid}")
                else:
                    print_error(f"Session bulunamadı: {sid}")
            else:
                print_error("Kullanım: /remove <sıra_no|session_id>")

        elif cmd == "/clean" or cmd.startswith("/clean "):
            # Parse args: /clean all, /clean keep=5
            args = command.split()
            if len(args) > 1 and args[1].lower() == "all":
                count = manager.cleanup_old(keep_last=0)
                print_success(f"Tum sessionlar temizlendi ({count} adet)")
            else:
                count = manager.cleanup_old(keep_last=5)
                print_success(f"{count} eski session temizlendi. Son 5 session kaldı.")

        elif cmd.startswith("/ara "):
            query = cmd[5:]
            results = manager.search(query)
            from ui.display import print_table as _pt_search
            rows = [[r["id"][:20], r["title"], r.get("summary", "")[:50]] for r in results]
            _pt_search("Arama Sonuçları", ["ID", "Başlık", "Özet"], rows)

        elif cmd == "/skills":
            skill_list = skills.list_skills()
            if skill_list:
                rows = [[s["name"], s.get("description", ""), str(s.get("use_count", 0))] for s in skill_list]
                print_table("Skill'ler", ["İsim", "Açıklama", "Kullanım"], rows)
            else:
                print_info("Hiç skill yok")

        elif cmd == "/review":
            """Manuel multi-persona code review tetikle."""
            print_info("Review baslatiliyor...")
            # Collect tool outputs for review (actual code, not chat)
            tool_outputs = []
            for m in loop.context.get_messages()[-20:]:
                if m.get("role") == "tool":
                    content = str(m.get("content", ""))
                    name = m.get("name", "")
                    if len(content) > 50:  # Only substantial outputs
                        tool_outputs.append(f"=== Tool: {name} ===\n{content[:1000]}")
            code_snippet = "\n\n".join(tool_outputs[-5:]) if tool_outputs else (
                "Review requested — no tool outputs available."
            )
            print_assistant("**Review:** Self-review kaldirildi, sadece test sonuclarina guven.")

        elif cmd == "/dashboard":
            from monitoring.dashboard import print_dashboard
            print_dashboard()
        
        elif cmd == "/crons":
            from ui.display import console
            from rich.table import Table
            from rich import box
            from cron.scheduler import cron
            jobs = cron.list_jobs()
            
            if not jobs:
                console.print("  [dim]Aktif cron görevi bulunmuyor.[/dim]")
            else:
                tbl = Table(title="Zamanlanmış Görevler (Crons)", border_style="#D4622A", box=box.ROUNDED)
                tbl.add_column("ID", style="cyan")
                tbl.add_column("Görev Adı", style="bold white")
                tbl.add_column("Zamanlama", style="magenta")
                tbl.add_column("Sıradaki Çalışma", style="green")
                
                for j in jobs:
                    tbl.add_row(j.id[:8], j.name, j.schedule, str(j.next_run or "Bilinmiyor"))
                
                console.print(tbl)
                
        elif cmd == "/tools":
            print_info(f"Kayıtlı tool: {registry.count()}")
            for t in registry.list():
                console.print(f"  [cyan]{t.name}[/cyan] [{t.toolset}] — {t.description}")

        elif cmd == "/tasks":
            from bg_tools.task_manager import task_manager
            from ui.display import print_table as _pt_tasks
            tasks = task_manager.list_tasks()
            if tasks:
                rows = [[t.id, t.name, t.status, t.elapsed] for t in tasks]
                _pt_tasks("Arka Plan Görevleri", ["ID", "Görev", "Durum", "Süre"], rows)
            else:
                print_info("Arka planda çalışan görev yok.")

        elif cmd.startswith("/verify "):
            arg = cmd[8:].strip()
            from tools.tool_verify import tool_verify_tool
            if arg == "--list":
                result = tool_verify_tool(tool_name="--list")
                console.print(f"\n[bold #D4622A]# Verify Durumu[/bold #D4622A]")
                console.print(result)
            elif arg == "--reset":
                result = tool_verify_tool(tool_name="--reset")
                data = json.loads(result) if isinstance(result, str) and result.startswith("{") else result
                print_success(data.get("message", "Cache temizlendi"))
            else:
                # Single tool verify
                console.print(f"\n[bold #D4622A]# Verifying: {arg}[/bold #D4622A]")
                result = tool_verify_tool(tool_name=arg)
                data = json.loads(result) if isinstance(result, str) and result.startswith("{") else result
                if isinstance(data, dict):
                    s = data.get("status", "?")
                    msg = data.get("message", "")
                    console.print(f"  Status: {s}")
                    console.print(f"  Mesaj:  {msg}")
                    if data.get("result_preview"):
                        console.print(f"  Çıktı:  {data['result_preview'][:200]}")
                else:
                    console.print(result)

        elif cmd == "/verify":
            console.print(f"\n[bold #D4622A]# Verifying all tools...[/bold #D4622A]")
            from tools.tool_verify import tool_verify_tool
            result = tool_verify_tool()
            data = json.loads(result) if isinstance(result, str) else result
            if isinstance(data, dict):
                for r in data.get("results", []):
                    icon = "✅" if r.get("status") == "✅" else ("⏭️" if r.get("status") == "⏭️" else "❌")
                    console.print(f"  {icon} {r['tool']:<15} {r.get('message', '')[:50]}")
                console.print(f"\n  {data.get('summary', '')}")
            else:
                console.print(result)

        elif cmd == "/status":
            status.show()

        elif cmd == "/setup":
            from ui.setup_wizard import run_setup_wizard
            await run_setup_wizard()

        elif cmd == "/help":
            from ui.display import console
            from rich.table import Table
            from rich import box
            tbl = Table(title="Komutlar", border_style="#D4622A", box=box.ROUNDED)
            tbl.add_column("Komut", style="#D4622A", width=16)
            tbl.add_column("İşlev", style="white")
            for cmd_name, desc in [
                ("/new", "Yeni oturum başlat"),
                ("/save <ad>", "Oturumu kaydet"),
                ("/load <id>", "Oturum yükle"),
                ("/sessions", "Oturumları listele"),
                ("/tasks", "Arka plan görevleri"),
                ("/crons", "Zamanlanmış görevler"),
                ("/ara <sorgu>", "Geçmiş konuşmalarda ara"),
                ("/skills", "Skill listesi"),
                ("/tools", "Tool listesi"),
                ("/model <isim>", "Model değiştir"),
                ("/personality", "Kişiliği göster"),
                ("/status", "Durum bilgisi"),
                ("/help", "Bu yardım"),
                ("/clear", "Ekranı temizle"),
                ("/exit", "Çıkış"),
                ("/export <fmt>", "Sohbeti disa aktar(json/md/html)"),
                ("/dashboard", "Metrik dashboard"),
            ]:
                tbl.add_row(cmd_name, desc)
            console.print(tbl)

        elif cmd == "/personality":
            from ui.display import console
            spath = Path("soul.md")
            if spath.exists():
                console.print(spath.read_text())
            else:
                console.print(f"[#D4622A]Kişilik:[/#D4622A] {soul.system_prompt[:200]}")

        elif cmd.startswith("/model "):
            new_model = cmd[7:]
            if new_model:
                # Validate: model must start with a known provider prefix
                valid_prefixes = ("deepseek/", "groq/", "openrouter/", "ollama/", "siliconflow/", "custom:")
                if any(new_model.startswith(p) for p in valid_prefixes):
                    settings.model.default = new_model
                    print_success(f"Model değiştirildi: {new_model}")
                else:
                    print_info(f"Desteklenmeyen model: {new_model}")
                    print_info(f"Geçerli format: provider/model (örn: deepseek/deepseek-v4-flash)")
            else:
                print_info(f"Mevcut model: {settings.model.default}")

        elif cmd == "/clear":
            import os
            import subprocess
            subprocess.run(["cmd", "/c", "cls"] if sys.platform == "win32" else ["clear"], check=False)

        else:
            print_info(f"Bilinmeyen komut: {command}. /help yazın.")


async def main():
    parser = argparse.ArgumentParser(description=f"{NAME} v{VERSION}")
    parser.add_argument("-q", "--query", help="Tek sorgu modu")
    parser.add_argument("--new", action="store_true", help="Yeni oturum")
    parser.add_argument("--version", action="store_true", help="Versiyon")
    args = parser.parse_args()

    if args.version:
        print(f"{NAME} v{VERSION}")
        return

    app = DorinaApp()
    await app.startup()

    if args.query:
        await app.run_single_query(args.query)
    else:
        try:
            await app.run_interactive()
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass

    try:
        import time
        from ui.display import console
        from rich.text import Text
        from ui.status_bar import status
        
        dur = time.time() - getattr(status, "start_time", time.time())
        if status.tokens_in > 0 or status.tokens_out > 0 or dur > 5:
            turn = getattr(status, "turn", 0)
            tokens_in = getattr(status, "tokens_in", 0)
            tokens_out = getattr(status, "tokens_out", 0)
            
            elapsed = ""
            if dur < 60:
                elapsed = f"{dur:.0f}s"
            elif dur < 3600:
                elapsed = f"{dur // 60:.0f}m {dur % 60:.0f}s"
            else:
                elapsed = f"{dur // 3600:.0f}h {(dur % 3600) // 60:.0f}m"

            t = Text()
            t.append("  ▸ ", style="dim")
            t.append(f"{elapsed}  │  {turn} tur  │  in: {tokens_in:,}  out: {tokens_out:,}", style="dim")
            console.print(t)
    except Exception:
        pass

    # Cleanup: close DB connections, resources
    await loop.cleanup()
    # Auto-delete empty sessions (0-1 messages) on exit
    from session.manager import manager as _mgr
    for s in _mgr.list_sessions(limit=100):
        msg_count = s.get("message_count", 0)
        if msg_count <= 1:
            _mgr.delete(s["id"])


def _restart_with_execv():
    """os.execv ile kendini yeniden başlat — aynı PID'de kalır."""
    import os as _os_mod
    python = sys.executable
    script = _os_mod.path.abspath(__file__)
    args = sys.argv[1:]
    _os_mod.execv(python, [python, script] + args)


def _sighup_handler(signum, frame):
    """SIGHUP → os.execv ile restart"""
    _restart_with_execv()


def entry():
    """Entry point for pip install -e . / dorina command."""
    import platform
    if platform.system() != "Windows":
        import signal
        signal.signal(signal.SIGHUP, _sighup_handler)
    asyncio.run(main())


if __name__ == "__main__":
    import signal
    try:
        signal.signal(signal.SIGHUP, _sighup_handler)
    except AttributeError:
        pass  # Windows: SIGHUP yok
    asyncio.run(main())
