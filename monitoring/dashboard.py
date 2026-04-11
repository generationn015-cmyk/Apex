"""
Live CLI Dashboard
Uses Rich library to render a real-time terminal dashboard.
Shows: balances, open trades, recent signals, PNL, stats.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

log = logging.getLogger("apex.dashboard")

try:
    from rich.console import Console
    from rich.layout import Layout
    from rich.live import Live
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

if TYPE_CHECKING:
    from execution.engine import ExecutionEngine, ManagedTrade
    from risk.manager import RiskManager


class Dashboard:
    def __init__(self, config: dict):
        cfg = config.get("monitoring", {}).get("dashboard", {})
        self.enabled: bool = cfg.get("enabled", True) and RICH_AVAILABLE
        self.refresh_sec: int = cfg.get("refresh_interval_sec", 5)
        self._console = Console() if RICH_AVAILABLE else None
        self._live: "Live | None" = None
        self._engine: "ExecutionEngine | None" = None
        self._risk: "RiskManager | None" = None
        self._bot_name: str = config.get("bot", {}).get("name", "APEX")
        self._mode: str = config.get("bot", {}).get("mode", "paper").upper()

    def attach(self, engine: "ExecutionEngine", risk: "RiskManager") -> None:
        self._engine = engine
        self._risk = risk

    def start(self) -> None:
        if not self.enabled:
            return
        from rich.live import Live
        self._live = Live(
            self._render(),
            console=self._console,
            refresh_per_second=1,
            screen=False,
        )
        self._live.start()

    def stop(self) -> None:
        if self._live:
            self._live.stop()
            self._live = None

    def refresh(self) -> None:
        if self._live:
            self._live.update(self._render())

    def print_signal(self, signal, approved: bool, reason: str = "") -> None:
        if not self._console:
            return
        if approved:
            self._console.print(
                f"[green]SIGNAL[/] {signal.strategy.upper()} | "
                f"[bold]{signal.pair}[/] {signal.direction.value.upper()} | "
                f"conf={signal.confidence:.0%} RR={signal.risk_reward:.1f}x "
                f"entry={signal.entry_price:.4f}"
            )
        else:
            self._console.print(
                f"[dim]SIGNAL REJECTED[/] {signal.strategy.upper()} | "
                f"{signal.pair} — {reason}"
            )

    def print_trade_open(self, trade: "ManagedTrade") -> None:
        if not self._console:
            return
        s = trade.signal
        self._console.print(
            f"[bold green]TRADE OPEN[/] {trade.trade_id} | "
            f"[bold]{s.pair}[/] {s.direction.value.upper()} @ {s.entry_price:.4f} | "
            f"stop={s.stop_price:.4f} target={s.target_price:.4f}"
        )

    def print_trade_closed(self, trade: "ManagedTrade") -> None:
        if not self._console:
            return
        color = "green" if trade.pnl >= 0 else "red"
        sign = "+" if trade.pnl >= 0 else ""
        self._console.print(
            f"[bold {color}]TRADE CLOSED[/] {trade.trade_id} | "
            f"{trade.signal.pair} | {trade.close_reason} | "
            f"PNL=[bold {color}]{sign}${trade.pnl:.4f}[/]"
        )

    # ── Render helpers ────────────────────────────────────────────────

    def _render(self):
        if not RICH_AVAILABLE:
            return ""
        from rich.columns import Columns
        from datetime import datetime

        layout = Layout()
        layout.split_column(
            Layout(self._header(), size=3),
            Layout(name="body"),
            Layout(self._footer(), size=3),
        )
        layout["body"].split_row(
            Layout(self._stats_panel(), name="left"),
            Layout(self._trades_panel(), name="right"),
        )
        return layout

    def _header(self):
        from datetime import datetime
        from rich.text import Text
        mode_color = "yellow" if self._mode == "PAPER" else "red"
        t = Text()
        t.append(f" {self._bot_name} TRADING BOT ", style="bold white on blue")
        t.append(f" [{self._mode}] ", style=f"bold white on {mode_color}")
        t.append(f" {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')} ", style="dim")
        return Panel(t, style="blue")

    def _stats_panel(self):
        if not self._risk:
            return Panel("No data", title="Stats")
        stats = self._risk.get_stats()
        table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
        table.add_column("Key", style="dim", width=18)
        table.add_column("Value", style="bold")

        balance = stats.get("balance", 0)
        pnl = stats.get("daily_pnl", 0)
        pnl_pct = stats.get("daily_pnl_pct", 0)
        pnl_color = "green" if pnl >= 0 else "red"
        dd = stats.get("drawdown_pct", 0)
        halted = stats.get("halted", False)

        table.add_row("Balance", f"${balance:.2f}")
        table.add_row("Daily PNL", f"[{pnl_color}]${pnl:+.2f} ({pnl_pct:+.1f}%)[/]")
        table.add_row("Drawdown", f"[{'red' if dd > 5 else 'green'}]{dd:.1f}%[/]")
        table.add_row("Win Rate", f"{stats.get('win_rate', 0):.0f}%")
        table.add_row("Trades Today", str(stats.get("trades_today", 0)))
        table.add_row("Open Positions", str(stats.get("open_positions", 0)))
        table.add_row("Status", "[red]HALTED[/]" if halted else "[green]ACTIVE[/]")

        return Panel(table, title="[bold]Performance[/]", border_style="blue")

    def _trades_panel(self):
        table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
        table.add_column("ID", style="dim", width=16)
        table.add_column("Pair", width=10)
        table.add_column("Dir", width=6)
        table.add_column("Entry", width=10)
        table.add_column("Stop", width=10)
        table.add_column("Target", width=10)
        table.add_column("Conf", width=6)

        open_trades = self._engine.get_open_trades() if self._engine else []
        for t in open_trades:
            s = t.signal
            dir_color = "green" if "long" in s.direction.value else "red"
            table.add_row(
                t.trade_id[-8:],
                s.pair,
                f"[{dir_color}]{s.direction.value.upper()[:5]}[/]",
                f"{s.entry_price:.4f}",
                f"[red]{s.stop_price:.4f}[/]",
                f"[green]{s.target_price:.4f}[/]",
                f"{s.confidence:.0%}",
            )

        if not open_trades:
            table.add_row("[dim]No open trades[/]", "", "", "", "", "", "")

        return Panel(table, title="[bold]Open Trades[/]", border_style="blue")

    def _footer(self):
        return Panel(
            "[dim]q=quit  p=toggle paper/live  s=show stats  h=halt[/]",
            style="dim"
        )
