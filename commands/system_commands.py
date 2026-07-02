"""System commands: /exit, /quit, /q, /help, /clear, /status, /setup."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app import DorinaApp


async def cmd_exit(app: "DorinaApp", cmd: str) -> None:
    """Exit the application."""
    from ui.display import print_info

    print_info("Görüşürüz!")
    app.running = False


async def cmd_quit(app: "DorinaApp", cmd: str) -> None:
    """Alias for /exit."""
    await cmd_exit(app, cmd)


async def cmd_q(app: "DorinaApp", cmd: str) -> None:
    """Alias for /exit."""
    await cmd_exit(app, cmd)


async def cmd_help(app: "DorinaApp", cmd: str) -> None:
    """Display the help table."""
    from ui.display import console
    from rich.table import Table
    from rich import box

    tbl = Table(title="Komutlar", border_style="#D4622A", box=box.ROUNDED)
    tbl.add_column("Komut", style="#D4622A", width=16)
    tbl.add_column("İşlev", style="white")
    for cmd_name, desc in [
        ("/new", "Yeni oturum başlat"),
        ("/temp", "Geçici sohbet (kayıtsız)"),
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


async def cmd_clear(app: "DorinaApp", cmd: str) -> None:
    """Clear the terminal screen."""
    import subprocess

    subprocess.run(["clear"], check=False)


async def cmd_status(app: "DorinaApp", cmd: str) -> None:
    """Show current status information."""
    from ui.status_bar import status

    status.show()


async def cmd_setup(app: "DorinaApp", cmd: str) -> None:
    """Run the interactive setup wizard."""
    from ui.setup_wizard import run_setup_wizard

    await run_setup_wizard()
