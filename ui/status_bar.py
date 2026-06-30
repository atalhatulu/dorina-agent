"""Status bar — prompt_toolkit toolbar state manager.

No Rich Live dependency. Provides toolbar tokens for prompt_toolkit's
bottom_toolbar, which is rendered inline with the prompt, not as a
separate overlay. This means the status bar is always at the bottom,
never overwrites user input, and is managed by prompt_toolkit itself.

Format: ⟳ {durum}  │  in: 12,450  out: 3,210  │  03:42  │  tur: 7
"""

import time
import asyncio

from core.constants import NAME, VERSION
from soul.personality import GODMODE, AUDIT_MODE

DORINA_ORANGE = "#E06C75"
TEXT_MAIN = "#ABB2BF"
DIM_GRAY = "#5C6370"
SUCCESS_GREEN = "#98C379"


class StatusBar:
    """State manager for prompt_toolkit bottom toolbar.
    
    Does NOT own any Live instance. Just tracks state and renders
    toolbar tokens on demand.
    """

    def __init__(self):
        self._lock = None  # Lazy: asyncio.Lock()
        self.model = ""
        self.provider = ""
        self.tokens_in = 0
        self.tokens_out = 0
        self.tool_calls = 0
        self.turn = 0
        self.start_time = time.time()
        self.turn_start_time = time.time()
        self.cost = 0.0
        self.context_pct = 0
        self.turn_tokens_in = 0
        self.turn_tokens_out = 0
        self._status_text = "idle"

    def _ensure_lock(self):
        if self._lock is None:
            self._lock = asyncio.Lock()

    def start_turn(self):
        self.turn += 1
        self.tool_calls = 0
        self.turn_tokens_in = 0
        self.turn_tokens_out = 0
        self.turn_start_time = time.time()
        self.set_status("Thinking")

    def add_tokens(self, prompt_tokens: int = 0, completion_tokens: int = 0, cost: float = 0.0):
        self._ensure_lock()
        self.tokens_in += prompt_tokens
        self.tokens_out += completion_tokens
        self.turn_tokens_in += prompt_tokens
        self.turn_tokens_out += completion_tokens
        self.cost += cost

    def end_turn(self):
        import time
        from ui.display import console, flush_stream
        flush_stream()
        console.print()
        from rich.text import Text
        
        # Calculate turn duration
        e = time.time() - getattr(self, 'turn_start_time', self.start_time)
        if e < 60:
            dur_str = f"{e:.1f}s"
        elif e < 3600:
            dur_str = f"{e // 60:.0f}m {e % 60:.0f}s"
        else:
            dur_str = f"{e // 3600:.0f}h {(e % 3600) // 60:.0f}m"

        t = Text()
        t.append(f"  ▸ Thought for {dur_str}  │  in: {self.turn_tokens_in:,}  out: {self.turn_tokens_out:,}  ", style="dim on #1a1a1a")
        console.print(t)
        console.print()

    def add_tool_call(self):
        self.tool_calls += 1

    def set_status(self, text: str):
        self._status_text = text

    @property
    def elapsed(self) -> str:
        import time
        e = time.time() - self.start_time
        if e < 60:
            return f"{e:.0f}s"
        elif e < 3600:
            return f"{e // 60:.0f}m {e % 60:.0f}s"
        return f"{e // 3600:.0f}h {(e % 3600) // 60:.0f}m"

    def get_toolbar_tokens(self) -> list[tuple[str, str]]:
        from soul.personality import GODMODE, AUDIT_MODE

        tokens = []
        
        if GODMODE:
            tokens.append(("class:godmode", " ⚡ GOD MODE "))
            tokens.append(("class:godmode_dim", "  │  "))
            tokens.extend([
                ("class:godmode_dim", f"{self.model or 'deepseek'}"),
                ("class:godmode_dim", "  │  "),
                ("class:godmode_dim", f"in: {self.tokens_in:,}  out: {self.tokens_out:,}"),
                ("class:godmode_dim", "  │  tur: "),
                ("class:godmode_dim", str(self.turn)),
            ])
        elif AUDIT_MODE:
            tokens.append(("class:audit", " 🔍 AUDIT "))
            tokens.append(("class:dim", "  │  "))
            tokens.extend([
                ("class:dim", f" {self.model or 'deepseek'}"),
                ("class:dim", "  │  "),
                ("class:green", f"in: {self.tokens_in:,}"),
                ("class:dim", f"  out: {self.tokens_out:,}"),
                ("class:dim", "  │  tur: "),
                ("class:dim", str(self.turn)),
                ("class:dim", f"  │  task: {self._get_task_count()}  cron: {self._get_cron_count()}  sub: {self._get_sub_count()}"),
            ])
        else:
            tokens.extend([
                ("class:dim", f" {self.model or 'deepseek'}"),
                ("class:dim", "  │  "),
                ("class:green", f"in: {self.tokens_in:,}"),
                ("class:dim", f"  out: {self.tokens_out:,}"),
                ("class:dim", "  │  tur: "),
                ("class:dim", str(self.turn)),
                ("class:dim", f"  │  task: {self._get_task_count()}  cron: {self._get_cron_count()}  sub: {self._get_sub_count()}"),
            ])
        return tokens

    def _get_task_count(self) -> int:
        try:
            from bg_tools.task_manager import task_manager
            return len(task_manager.list_tasks())
        except Exception:
            return 0

    def show(self):
        """Print current status info to console."""
        from rich.console import Console
        from rich.table import Table
        from rich import box
        console = Console()
        tbl = Table(border_style="#D4622A", box=box.ROUNDED)
        tbl.add_column("Alan", style="bold #D4622A")
        tbl.add_column("Değer", style="white")
        elapsed = self.elapsed()
        tbl.add_row("Model", f"{self.provider}/{self.model}" if self.model else "ayarlanmamış")
        tbl.add_row("Durum", self._status_text)
        tbl.add_row("Süre", elapsed)
        tbl.add_row("Tur", str(self.turn))
        tbl.add_row("Tool Calls", str(self.tool_calls))
        tbl.add_row("Token (in/out)", f"{self.tokens_in:,} / {self.tokens_out:,}")
        tbl.add_row("Maliyet", f"${self.cost:.6f}")
        if GODMODE:
            tbl.add_row("Godmode", "⚡ AKTİF", style="bold red")
        if AUDIT_MODE:
            tbl.add_row("Audit", "🔍 ACIK", style="bold #E06C75")
        console.print(tbl)

    def _get_cron_count(self) -> int:
        try:
            from cron.scheduler import cron
            return len(cron.jobs)
        except Exception:
            return 0
            
    def _get_sub_count(self) -> int:
        try:
            from agents.crew import crew
            return len([f for f in crew.list_forks() if f.get("status") == "running"])
        except Exception:
            return 0

    def show_waiting(self):
        """AI calisirken gosterilecek bekleme mesaji."""
        mdl = self.model or "?"
        if GODMODE:
            print(f"\r\x1b[38;5;208m⟳ {self._status_text} {mdl}\x1b[0m  │  tur: {self.turn}  ", end="", flush=True)
        else:
            print(f"\r⟳ {self._status_text} {mdl}  │  tur: {self.turn}  ", end="", flush=True)
        print(f"\r\033[2K⟳ {self._status_text} {mdl}  │  tur: {self.turn}  ", end="", flush=True)

    def hide_waiting(self):
        """Bekleme mesajini temizle."""
        # Clear line completely
        print("\r\033[2K", end="", flush=True)

    # No-op methods for backwards compatibility with existing callers
    def start_live(self):
        pass

    def stop_live(self):
        pass

    def pause(self):
        pass

    def resume(self):
        pass

    def _refresh(self):
        pass

    def reset(self):
        self.tokens_in = 0
        self.tokens_out = 0
        self.turn_tokens_in = 0
        self.turn_tokens_out = 0
        self.tool_calls = 0
        self.turn = 0
        self.cost = 0.0
        self.context_pct = 0
        self.start_time = time.time()
        self._status_text = "idle"


status = StatusBar()
