"""REPL - prompt_toolkit ile komut satırı girdisi.
Single PromptSession with bottom toolbar for status bar.

Slash komutları için autocomplete: / yaz → dropdown liste açılır.
Yazdıkça daralır, Tab ile tamamlanır.
"""

from __future__ import annotations
import sys
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.styles import Style

HISTORY_FILE = Path("data/history.txt")

# Slash commands - A-Z sorted
SLASH_COMMANDS = sorted([
    "/ara", "/clear", "/exit", "/export", "/help", "/load",
    "/model", "/new", "/personality", "/q", "/quit",
    "/review", "/save", "/sessions", "/setup", "/skills", "/status", "/tools",
])

# Style for prompt and toolbar
STYLE = Style.from_dict({
    "prompt": "bold #D4622A",
    "completion-menu": "bg:#1e1e2e #cdd6f4",
    "completion-menu.completion": "bg:#1e1e2e #cdd6f4",
    "completion-menu.completion.current": "bg:#45475a #D4622A bold",
    "completion-menu.meta": "bg:#1e1e2e #6c7086",
    "completion-menu.meta.current": "bg:#45475a #D4622A",
    # Toolbar styles matching theme
    "orange": "bold #E06C75",
    "main": "#ABB2BF",
    "dim": "#5C6370",
    "green": "#98C379",
})

_session: PromptSession | None = None


def create_session() -> PromptSession:
    """Create single PromptSession with bottom toolbar."""
    global _session

    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)

    cmd_completer = WordCompleter(
        words=SLASH_COMMANDS,
        ignore_case=True,
        match_middle=False,
        meta_dict={
            "/ara": "Gecmiste konusma ara",
            "/clear": "Ekrani temizle",
            "/exit": "Cikis yap",
            "/export": "Oturumu disa aktar",
            "/help": "Komut listesi",
            "/load": "Kayitli oturumu yukle",
            "/model": "Model degistir",
            "/new": "Yeni oturum baslat",
            "/personality": "Kisiligi goster",
            "/q": "Cikis (kisa yol)",
            "/quit": "Cikis",
            "/review": "Multi-persona kod incelemesi",
            "/save": "Oturumu kaydet",
            "/sessions": "Oturumlari listele",
            "/setup": "Kurulum sihirbazi",
            "/skills": "Skill listesi",
            "/status": "Durum bilgisi",
            "/tools": "Tool listesi",
        },
    )

    from ui.status_bar import status

    _session = PromptSession(
        history=FileHistory(str(HISTORY_FILE)),
        auto_suggest=AutoSuggestFromHistory(),
        completer=cmd_completer,
        complete_while_typing=True,
        style=STYLE,
        enable_history_search=True,
        # Bottom toolbar from status bar
        bottom_toolbar=status.get_toolbar_tokens,
    )
    return _session


async def get_input(session: PromptSession | None = None) -> str:
    """Kullanıcıdan girdi al. TTY yoksa fallback input()."""
    from prompt_toolkit.patch_stdout import patch_stdout

    s = session or _session

    if s is None or not sys.stdin.isatty():
        try:
            return input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            return "/exit"

    try:
        # patch_stdout: prevents background output from corrupting input
        with patch_stdout():
            return (await s.prompt_async("> ", style=STYLE)).strip()
    except (EOFError, KeyboardInterrupt):
        return "/exit"
