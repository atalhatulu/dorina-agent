"""Data & metrics commands: /dashboard."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import DorinaApp


async def cmd_dashboard(app: "DorinaApp", cmd: str) -> None:
    """Show the monitoring dashboard with metrics."""
    from monitoring.dashboard import print_dashboard

    print_dashboard()
