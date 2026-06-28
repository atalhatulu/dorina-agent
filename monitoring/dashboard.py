"""Rich terminal dashboard — canlı metrik görüntüleme.

Özellikler:
  - Token tüketimi ve maliyet paneli
  - Tool kullanım tablosu
  - Provider bazında istatistikler
  - Insight önerileri
  - Otomatik yenileme (opsiyonel)
"""

from __future__ import annotations
import time
from typing import Optional

from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.console import Console
from rich.text import Text
from rich import box

from core.logger import log


def build_metrics_table(metrics_data: dict) -> Table:
    """Metrik özeti tablosu oluştur."""
    table = Table(title="📊 Session Metrics", box=box.ROUNDED, title_style="bold cyan")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Total Tokens", f"{metrics_data.get('tokens', 0):,}")
    table.add_row("Input Tokens", f"{metrics_data.get('input_tokens', 0):,}")
    table.add_row("Output Tokens", f"{metrics_data.get('output_tokens', 0):,}")
    table.add_row("Cached Input", f"{metrics_data.get('cached_input_tokens', 0):,}")
    table.add_row("Total Cost", f"${metrics_data.get('total_cost_per_session', 0):.6f}")
    table.add_row("Requests", str(metrics_data.get('requests', 0)))
    table.add_row("Errors", str(metrics_data.get('errors', 0)))
    table.add_row("Session Duration", f"{metrics_data.get('session_duration_sec', 0):.1f}s")
    table.add_row("Active Tools", str(metrics_data.get('tool_count', 0)))

    return table


def build_tool_usage_table(tool_stats: list[dict]) -> Table:
    """Tool kullanım tablosu."""
    table = Table(title="🔧 Tool Usage", box=box.SIMPLE, title_style="bold yellow")
    table.add_column("Tool", style="green")
    table.add_column("Calls", justify="right")
    table.add_column("Errors", justify="right")
    table.add_column("Error Rate", justify="right")
    table.add_column("Avg Latency", justify="right")

    for t in tool_stats[:15]:  # İlk 15 tool
        error_rate = f"{t.get('error_rate', 0) * 100:.1f}%"
        latency = f"{t.get('avg_latency_ms', 0):.0f}ms"
        table.add_row(
            t.get("name", "?"),
            str(t.get("calls", 0)),
            str(t.get("errors", 0)),
            error_rate,
            latency,
        )

    if not tool_stats:
        table.add_row("(no data)", "", "", "", "")

    return table


def build_provider_table(provider_stats: list[dict]) -> Table:
    """Provider bazında istatistik tablosu."""
    table = Table(title="🏢 Provider Stats", box=box.SIMPLE, title_style="bold blue")
    table.add_column("Provider", style="magenta")
    table.add_column("Calls", justify="right")
    table.add_column("Cost", justify="right")

    for p in provider_stats:
        table.add_row(
            p.get("provider", "?"),
            str(p.get("calls", 0)),
            f"${p.get('cost', 0):.6f}",
        )

    if not provider_stats:
        table.add_row("(no data)", "", "")

    return table


def build_insight_panel(recommendations: list[str]) -> Panel:
    """Insight önerileri paneli."""
    if not recommendations:
        recommendations = ["✅ No issues detected."]

    content = "\n".join(f"  {r}" for r in recommendations)
    return Panel(
        Text(content, style="white"),
        title="💡 Insights",
        border_style="green",
        box=box.ROUNDED,
    )


def build_full_dashboard(
    metrics_data: dict,
    tool_stats: list[dict],
    provider_stats: list[dict],
    recommendations: list[str],
) -> Layout:
    """Tam dashboard layout'u oluştur."""
    layout = Layout()

    layout.split_column(
        Layout(name="top", size=3),
        Layout(name="main"),
        Layout(name="bottom"),
    )

    # Header
    header = Panel(
        Text("Dorina Agent Dashboard", style="bold white on blue"),
        box=box.SIMPLE,
    )
    layout["top"].update(header)

    # Main content: metrics + tools + providers
    layout["main"].split_row(
        Layout(name="metrics"),
        Layout(name="tools"),
        Layout(name="providers"),
    )

    layout["metrics"].update(build_metrics_table(metrics_data))
    layout["tools"].update(build_tool_usage_table(tool_stats))
    layout["providers"].update(build_provider_table(provider_stats))

    # Bottom: insights
    layout["bottom"].update(build_insight_panel(recommendations))

    return layout


def print_dashboard(metrics_instance=None, insights_instance=None):
    """Terminal'e dashboard yazdır (tek seferlik)."""
    from monitoring.metrics import metrics as default_metrics
    from monitoring.insights import insights as default_insights

    m = metrics_instance or default_metrics
    i = insights_instance or default_insights

    console = Console()
    metrics_data = m.summary()
    tool_stats = m.tool_summary()
    provider_stats = m.provider_summary()
    recs = i.recommendations()

    header = Panel(
        Text("📊 Dorina Agent Dashboard", style="bold white on blue"),
        box=box.SIMPLE,
    )
    console.print(header)

    # satır 1: metrics + tools
    console.print("\n")
    console.print(Panel.fit(
        build_metrics_table(metrics_data),
    ))
    console.print("\n")
    console.print(Panel.fit(
        build_tool_usage_table(tool_stats),
    ))
    console.print("\n")
    console.print(Panel.fit(
        build_provider_table(provider_stats),
    ))
    console.print("\n")
    console.print(build_insight_panel(recs))


def live_dashboard(metrics_instance=None, insights_instance=None, refresh_sec: int = 2):
    """Canlı dashboard (sürekli güncellenir, Ctrl+C ile çık)."""
    from monitoring.metrics import metrics as default_metrics
    from monitoring.insights import insights as default_insights

    m = metrics_instance or default_metrics
    i = insights_instance or default_insights

    try:
        with Live(refresh_per_second=1 / refresh_sec, screen=True) as live:
            while True:
                metrics_data = m.summary()
                tool_stats = m.tool_summary()
                provider_stats = m.provider_summary()
                recs = i.recommendations()

                layout = build_full_dashboard(metrics_data, tool_stats, provider_stats, recs)
                live.update(layout)
                time.sleep(refresh_sec)
    except KeyboardInterrupt:
        log.info("Dashboard closed by user")
    except Exception as e:
        log.error(f"Dashboard error: {e}")
