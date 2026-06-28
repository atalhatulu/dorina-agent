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
        self._status_text = "idle"

    def _ensure_lock(self):
        if self._lock is None:
            self._lock = asyncio.Lock()

    def start_turn(self):
        self.turn += 1
        self.tool_calls = 0
        self.turn_start_time = time.time()
        self.set_status("thinking")

    def add_tokens(self, prompt_tokens: int = 0, completion_tokens: int = 0, cost: float = 0.0):
        self._ensure_lock()
        self.tokens_in += prompt_tokens
        self.tokens_out += completion_tokens
        self.cost += cost

        if completion_tokens > 0:
            from ui.display import console, flush_stream
            flush_stream()
            console.print()
            from rich.text import Text
            
            # Calculate turn duration
            e = time.time() - getattr(self, 'turn_start_time', self.start_time)
            if e < 60:
                dur_str = f"{e:.0f}s"
            elif e < 3600:
                dur_str = f"{e // 60:.0f}m {e % 60:.0f}s"
            else:
                dur_str = f"{e // 3600:.0f}h {(e % 3600) // 60:.0f}m"

            t = Text()
            t.append("▸ ", style="dim")
            t.append(f"Thought for {dur_str}, {completion_tokens} tokens", style="dim")
            console.print(t)
            console.print()

    def add_tool_call(self):
        self.tool_calls += 1

    def set_status(self, text: str):
        self._status_text = text

    @property
    def elapsed(self) -> str:
        e = time.time() - self.start_time
        if e < 60:
            return f"{e:.0f}s"
        elif e < 3600:
            return f"{e // 60:.0f}m {e % 60:.0f}s"
        return f"{e // 3600:.0f}h {(e % 3600) // 60:.0f}m"

    def get_toolbar_tokens(self) -> list[tuple[str, str]]:
        status = self._status_text
        tin = self.tokens_in
        tout = self.tokens_out
        t = self.turn
        t_str = self.elapsed
        mdl = self.model or "?"

        return [
            ("class:orange", " ⟳ "),
            ("class:main", status),
            ("class:dim", f" {mdl}"),
            ("class:dim", "  │  "),
            ("class:green", f"in: {tin:,}"),
            ("class:main", f"  out: {tout:,}"),
            ("class:dim", "  │  "),
            ("class:main", t_str),
            ("class:dim", "  │  "),
            ("class:dim", f"tur: {t}"),
        ]

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
        self.tool_calls = 0
        self.turn = 0
        self.cost = 0.0
        self.context_pct = 0
        self.start_time = time.time()
        self._status_text = "idle"


status = StatusBar()
