"""Status bar — toolbars for both prompt_toolkit (input phase) and Rich Live (AI phase).

prompt_toolkit bottom_toolbar renders during user input.
Rich Live display renders a persistent bottom bar during AI processing.
Both show the same information in the same format.
"""

import time
import asyncio
import shutil
import subprocess

from core.mode_manager import modes
from core.event_bus import bus
from rich.text import Text

# Color Palette (By Mode) - as per plan
COLOR_PALETTE = {
    "normal": {
        "primary": "#D4622A",  # orange
        "secondary": "#E08F5A",
        "dim": "#5C6370",
        "accent": "#98C379",  # green
    },
    "godmode": {
        "primary": "#ff3333",  # red
        "secondary": "#cc2222",
        "dim": "#662222",
        "accent": "#ff6666",
    },
    "audit": {
        "primary": "#E06C75",  # warm red
        "secondary": "#D4622A",
        "dim": "#5C6370",
        "accent": "#98C379",
    },
    "temp": {
        "primary": "#6C7086",  # gray
        "secondary": "#585B70",
        "dim": "#3b3b3b",
        "accent": "#6C7086",
    },
}

# --- Style mappings (for prompt_toolkit) ---
# These will need to be defined in ui/repl.py (or a central style definition)
# For now, we'll use placeholder strings and assume they are defined elsewhere.
# "class:godmode" -> "fg: #ff3333 bold"
# "class:godmode_dim" -> "fg: #662222"
# "class:normal_primary" -> "fg: #D4622A bold"
# "class:normal_dim" -> "fg: #5C6370"
# "class:audit_primary" -> "fg: #E06C75 bold"
# "class:audit_dim" -> "fg: #5C6370"
# "class:temp_primary" -> "fg: #6C7086 bold"
# "class:temp_dim" -> "fg: #3b3b3b"
# "class:accent" -> "fg: #98C379"




class StatusBar:
    """Two-phase status bar: prompt_toolkit bottom_toolbar + Rich Live.

    - During user input: prompt_toolkit renders bottom_toolbar tokens.
    - During AI processing: Rich Live display renders a persistent
      bottom bar (toolbar would disappear since prompt_toolkit is idle).
    - Both show the same information in the same visual format.
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
        self._last_update = time.time()
        self.git_branch = self._get_git_branch()
        self.mode_color = COLOR_PALETTE["normal"]

    def _ensure_lock(self):
        if self._lock is None:
            self._lock = asyncio.Lock()

    @staticmethod
    def _active_mode() -> str:
        """Return current mode string."""
        if modes.is_on('godmode'):
            return "godmode"
        elif modes.is_on('audit'):
            return "audit"
        elif modes.is_on('temp'):
            return "temp"
        return "normal"

    def _get_git_branch(self) -> str:
        """Read current git branch."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, check=False
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass
        return ""

    def _context_bar(self, pct: float, width: int = 20) -> str:
        """Render context usage bar: ████████░░░░"""
        filled = int(pct * width)
        empty = width - filled
        bar = "█" * filled + "░" * empty
        pct_str = f"{int(pct * 100)}%"
        return f"{bar} {pct_str}"

    @property
    def tokens_pretty(self) -> str:
        """Formatted token counts (1.2K, 3.4M)."""
        if self.tokens_in + self.tokens_out < 1000:
            return f"in: {self.tokens_in:,} out: {self.tokens_out:,}"
        if self.tokens_in + self.tokens_out < 1_000_000:
            return f"in: {self.tokens_in/1000:.1f}K out: {self.tokens_out/1000:.1f}K"
        return f"in: {self.tokens_in/1_000_000:.1f}M out: {self.tokens_out/1_000_000:.1f}M"

    @property
    def cost_pretty(self) -> str:
        """Formatted cost string ($0.0042)."""
        return f"${self.cost:.4f}"

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
        """Single-line toolbar styled as a full-width divider with embedded status.

        Renders as: ───────────────── ⚕ model │ 128K │ █░ 13% │ 27m ────────────────
        """
        width = shutil.get_terminal_size().columns
        mode = self._active_mode()
        self.mode_color = COLOR_PALETTE[mode]

        # Mode icon
        if mode == "godmode":
            mode_tag = "⚡"
        elif mode == "audit":
            mode_tag = "🔍"
        elif mode == "temp":
            mode_tag = "💭"
        else:
            mode_tag = ""

        # Model (short name)
        model_short = self.model or 'deepseek-chat'
        if '/' in model_short:
            model_short = model_short.split('/')[-1]
        if len(model_short) > 18:
            model_short = model_short[:16] + ".."

        # Build content string
        content_parts = []
        if mode_tag:
            content_parts.append(f" {mode_tag}")
        content_parts.append(f" {model_short}")

        suffix = ""
        if self.context_pct > 0:
            ctx = self._context_bar(self.context_pct, width=min(12, max(4, width // 16)))
            suffix += f"  {ctx}"

        suffix += f"  {self.elapsed}"

        if self.tokens_in + self.tokens_out > 0:
            suffix += f"  {self.tokens_pretty}"

        if self.cost > 0.001:
            suffix += f"  {self.cost_pretty}"

        suffix += f"  turn {self.turn}"

        # git branch removed — not shown in status bar

        content = "".join(content_parts) + suffix
        content_stripped = content.strip()

        # If content is empty, just draw a plain divider
        if not content_stripped:
            n = max(0, width - 2)
            return [(f"class:{mode}_dim", f"{'─' * n}")]

        # If terminal is too narrow, show content without fillers
        if width < 20 or len(content_stripped) > width - 4:
            return [(f"class:{mode}_dim", content_stripped[:width])]

        # Pad with ─ to fill full width
        filler = "─"
        total_fill = max(0, width - len(content_stripped) - 4)
        left_fill = total_fill // 2
        right_fill = total_fill - left_fill

        left_str = f" {filler * left_fill} " if left_fill > 0 else "  "
        right_str = f" {filler * right_fill} " if right_fill > 0 else "  "

        tokens = []
        tokens.append((f"class:{mode}_dim", left_str))
        tokens.append((f"class:{mode}_primary", content_stripped))
        tokens.append((f"class:{mode}_dim", right_str))
        return tokens

    def _get_task_count(self) -> int:
        """Number of background tasks currently running."""
        try:
            from bg_tools.task_manager import task_manager
            return len([t for t in task_manager.list_tasks() if t.status == "running"])
        except (ImportError, AttributeError):
            return 0

    def show(self):
        """Print current status info to console."""
        from rich.console import Console
        from rich.table import Table
        from rich import box
        console = Console()
        tbl = Table(border_style="#D4622A", box=box.ROUNDED)
        tbl.add_column("Field", style="bold #D4622A")
        tbl.add_column("Value", style="white")
        tbl.add_row("Model", f"{self.provider}/{self.model}" if self.model else "unset")
        tbl.add_row("Status", self._status_text)
        tbl.add_row("Duration", str(self.elapsed))
        tbl.add_row("Turn", str(self.turn))
        tbl.add_row("Tool Calls", str(self.tool_calls))
        tbl.add_row("Token (in/out)", f"{self.tokens_in:,} / {self.tokens_out:,}")
        tbl.add_row("Cost", f"${self.cost:.6f}")
        if modes.is_on('godmode'):
            tbl.add_row("Godmode", "⚡ ACTIVE", style="bold red")
        if modes.is_on('audit'):
            tbl.add_row("Audit", "🔍 ON", style="bold #E06C75")
        console.print(tbl)


    def update(self):
        """Force refresh — marks toolbar for re-render on next prompt_toolkit cycle."""
        self._last_update = time.time()
        # get_toolbar_tokens() reads modes directly, so the toolbar
        # will pick up any mode change on the next render cycle.

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
        self.git_branch = self._get_git_branch() # Reset git branch as well


status = StatusBar()


def _setup_mode_listener():
    """Subscribe to mode_change events so the status bar refreshes visually."""
    bus.subscribe("mode_change", lambda **kw: status.update())


_setup_mode_listener()
