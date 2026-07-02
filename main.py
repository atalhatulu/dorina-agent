#!/usr/bin/env python3
"""
Dorina Agent — Self-hosted CLI AI agent.

Kullanim:
    python main.py                    # Interaktif mod
    python main.py -q "soru"         # Tek sorgu
    python main.py --new              # Yeni oturum
"""

from __future__ import annotations
import asyncio
import signal
import sys
from pathlib import Path

# Proje kokunu PYTHONPATH'e ekle
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Log supurasyonu + API key yukleme (diger import'lardan ONCE)
from core.bootstrap import suppress_noisy_logs, ensure_project_root, init_api_keys
suppress_noisy_logs()
ensure_project_root()
init_api_keys()

# Simdi geri kalan import'lar guvenle yuklenebilir
from core.logger import log, console
from core.constants import NAME, VERSION
from core.version_manager import get_version_manager
from session.manager import manager
from orchestrator.experimental_loop import loop_v2 as loop
from ui.display import console as _ui_console


async def main():
    import argparse

    parser = argparse.ArgumentParser(description=f"{NAME} v{VERSION}")
    parser.add_argument("-q", "--query", help="Tek sorgu modu")
    parser.add_argument("--new", action="store_true", help="Yeni oturum")
    parser.add_argument("--version", action="store_true", help="Versiyon")
    args = parser.parse_args()

    if args.version:
        print(f"{NAME} v{VERSION}")
        return

    from app import DorinaApp
    app = DorinaApp()
    await app.startup()

    if args.query:
        await app.run_single_query(args.query)
    else:
        try:
            await app.run_interactive()
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass

    # Turn summary
    try:
        import time
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
    except (KeyError, ValueError, OSError):
        pass

    await loop.cleanup()
    from session.manager import manager as _mgr
    for s in _mgr.list_sessions(limit=100):
        msg_count = s.get("message_count", 0)
        if msg_count <= 1:
            _mgr.delete(s["id"])


def entry():
    """Entry point for pip install -e . / dorina command."""
    signal.signal(signal.SIGHUP, _sighup_handler)
    asyncio.run(main())


def _sighup_handler(signum, frame):
    """SIGHUP -> os.execv ile restart"""
    import os as _os_mod
    python = sys.executable
    script = _os_mod.path.abspath(__file__)
    args = sys.argv[1:]
    _os_mod.execv(python, [python, script] + args)


if __name__ == "__main__":
    signal.signal(signal.SIGHUP, _sighup_handler)
    asyncio.run(main())
