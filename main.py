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

# Command registry (extracted from _handle_command monolith)
from commands import register_commands
CMD_REGISTRY = register_commands()

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
        
        import subprocess
        subprocess.run(["cmd", "/c", "cls"] if sys.platform == "win32" else ["clear"], check=False)

        from ui.display import console
        console.print("\n  [dim]Hazırlanıyor... (Bellek ve Araçlar indeksleniyor)[/dim]")

        # Eager initialization at startup
        await rag.initialize()

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
                _trimmed = user_input.strip().lower()
                if user_input.startswith("/"):
                    _sb_status.resume()
                    await self._handle_command(user_input)
                    _sb_status.pause()
                    continue

                # Dogal dil komut yonlendirmesi
                if _trimmed in ("bu konusmayi kaydet", "konusmayi kaydet", "kaydet", "save this conversation"):
                    _sb_status.resume()
                    _title = user_input.replace("kaydet", "").replace("save", "").replace("bu konusmayi", "").strip()
                    await self._handle_command(f"/save {_title}" if _title else "/save")
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
                        # Temizlik: yarim kalmis tool_calls assistant msg'lerini sil
                        # (DeepSeek: "assistant(tool_calls) sonrasi tool msg gelmeli" kurali)
                        msgs = loop.context.messages
                        cleaned = []
                        for m in msgs:
                            if m.get("role") == "assistant" and m.get("tool_calls") and not m.get("content"):
                                continue  # yarim kalmis tool_calls msg'ini at
                            if m.get("role") == "system" and "Ctrl+C" in (m.get("content") or ""):
                                continue  # eski system msg'lerini de temizle
                            cleaned.append(m)
                        # Son mesaj tool ise onu da temizle (karsiligi olmayan tool result)
                        while cleaned and cleaned[-1].get("role") == "tool":
                            cleaned.pop()
                        loop.context.messages = cleaned
                        if not loop.context.messages or loop.context.messages[-1].get("role") != "user":
                            loop.context.messages.append({"role": "user", "content": "Kullanıcı işlemi (Ctrl+C) ile yarıda kesti."})
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

                # ─── Turn summary (after response) ───
                _sb_status.end_turn()

                # ─── Spacing (shown at status bar loop start) ───
                display.print_divider()

                # Otomatik kaydet
                if settings.session.auto_save and loop.context.get_messages() and not loop._temp_mode:
                    manager.save(
                        loop.context.get_messages(),
                        summary=response[:200] if response else "",
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
        """Slash komutlarını registry üzerinden işle."""
        from ui.display import print_info

        prefix = command.lower().split()[0]
        handler = CMD_REGISTRY.get(prefix)
        if handler:
            await handler(self, command)
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
