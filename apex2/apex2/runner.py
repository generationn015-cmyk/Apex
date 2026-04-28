"""Apex v2 runner / CLI.

Modes:
  backtest    Run a strategy against historical bars; print metrics.
  paper       Connect to broker (Alpaca paper by default), evaluate strategy
              on each bar tick, route orders through ExecutionRouter.
  live        Same as paper but with real money. Gated behind config + flag.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import typer
from rich.console import Console
from rich.table import Table

from .backtest.analyzers import AnalyzerSuite
from .backtest.engine import BacktestEngine
from .backtest.metrics import compute_metrics
from .brokers.alpaca import AlpacaBroker
from .config.loader import load_config
from .config.models import Config
from .data.source import DataSource
from .execution.router import ExecutionRouter, ExecRequest
from .risk.manager import GateInput, RiskManager
from .strategies.base import StrategyContext
from .strategies.registry import build as build_strategy

app = typer.Typer(add_completion=False)
console = Console()


def _setup_logging(level: str, log_file: str | None = None) -> None:
    handlers = [logging.StreamHandler()]
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file))
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )


@app.command()
def backtest(
    config: str = typer.Option("configs/default.yaml", "--config", "-c"),
    strategy: str = typer.Option(..., "--strategy", "-s"),
    years: int = typer.Option(5, "--years", "-y"),
    end: str | None = typer.Option(None, "--end"),
):
    """Run a strategy over `years` of history ending at `end` (default today)."""
    cfg = load_config(config)
    _setup_logging(cfg.monitoring.log_level, cfg.monitoring.log_file)

    end_dt = datetime.fromisoformat(end) if end else datetime.utcnow()
    start_dt = end_dt - timedelta(days=int(years * 365.25))

    strat_cfg = getattr(cfg.strategies, strategy)
    if not strat_cfg.enabled:
        console.print(f"[yellow]Strategy {strategy} is disabled in config[/yellow]")
        raise typer.Exit(1)

    universe = list(strat_cfg.params.get("universe", []))
    bench = strat_cfg.params.get("benchmark", "SPY")
    if bench and bench not in universe:
        universe.append(bench)
    if not universe:
        console.print(f"[red]Strategy {strategy} has empty universe[/red]")
        raise typer.Exit(1)

    src = DataSource(cfg.data, cfg.brokers.alpaca if cfg.brokers.alpaca.enabled else None)
    bars = {}
    for sym in universe:
        try:
            df = src.get_bars(sym, start_dt.date(), end_dt.date(), timeframe="1d")
            if not df.empty:
                bars[sym] = df
        except Exception as e:
            console.print(f"[yellow]Skip {sym}: {e}[/yellow]")
    if not bars:
        console.print("[red]No data fetched. Check credentials / network.[/red]")
        raise typer.Exit(1)

    ctx = StrategyContext(
        params=strat_cfg.params,
        risk_pct_per_trade=cfg.capital.risk_per_trade_pct,
        max_position_pct=cfg.capital.max_position_pct,
    )
    strat = build_strategy(strategy, ctx)

    bt_cfg = cfg.backtest
    bt_cfg.initial_cash = cfg.capital.starting_balance_usd
    engine = BacktestEngine(bt_cfg)
    state = engine.run(bars, strat, start=start_dt, end=end_dt)

    metrics = compute_metrics(state.equity_curve, state.fills)
    _print_metrics(strategy, metrics, cfg.capital.starting_balance_usd, state.equity_curve)
    extras = AnalyzerSuite.default().run(state.equity_curve, state.fills)
    _print_analyzers(extras)


@app.command()
def portfolio(
    config: str = typer.Option("configs/default.yaml", "--config", "-c"),
    strategies: str = typer.Option("rsi2_meanrev,donchian_trend", "--strategies"),
    years: int = typer.Option(5, "--years", "-y"),
    end: str | None = typer.Option(None, "--end"),
):
    """Backtest multiple strategies sharing one capital pool. Reports combined metrics."""
    cfg = load_config(config)
    _setup_logging(cfg.monitoring.log_level, cfg.monitoring.log_file)

    end_dt = datetime.fromisoformat(end) if end else datetime.utcnow()
    start_dt = end_dt - timedelta(days=int(years * 365.25))

    names = [s.strip() for s in strategies.split(",") if s.strip()]
    universe: set[str] = set()
    for n in names:
        sc = getattr(cfg.strategies, n)
        universe.update(sc.params.get("universe", []))
        bench = sc.params.get("benchmark")
        if bench:
            universe.add(bench)

    src = DataSource(cfg.data, cfg.brokers.alpaca if cfg.brokers.alpaca.enabled else None)
    bars = {}
    for sym in sorted(universe):
        try:
            df = src.get_bars(sym, start_dt.date(), end_dt.date(), timeframe="1d")
            if not df.empty:
                bars[sym] = df
        except Exception as e:
            console.print(f"[yellow]Skip {sym}: {e}[/yellow]")
    if not bars:
        console.print("[red]No data fetched.[/red]")
        raise typer.Exit(1)

    # Build combined strategy that delegates to each sub-strategy.
    sub_strategies = []
    capital_per = cfg.capital.starting_balance_usd / len(names)
    for n in names:
        sc = getattr(cfg.strategies, n)
        ctx = StrategyContext(
            params=sc.params,
            risk_pct_per_trade=cfg.capital.risk_per_trade_pct,
            max_position_pct=cfg.capital.max_position_pct / max(len(names), 1),
        )
        sub_strategies.append(build_strategy(n, ctx))

    def combined(state, ts, b):
        out = []
        for s in sub_strategies:
            out.extend(s.on_bar(state, ts, b) or [])
        return out

    bt_cfg = cfg.backtest
    bt_cfg.initial_cash = cfg.capital.starting_balance_usd
    state = BacktestEngine(bt_cfg).run(bars, combined, start=start_dt, end=end_dt)
    metrics = compute_metrics(state.equity_curve, state.fills)
    _print_metrics(f"portfolio[{','.join(names)}]", metrics, cfg.capital.starting_balance_usd, state.equity_curve)
    extras = AnalyzerSuite.default().run(state.equity_curve, state.fills)
    _print_analyzers(extras)
    console.print(f"[green]Used {capital_per:.0f}/strategy capital allocation across {len(names)} strategies[/green]")


@app.command()
def paper(
    config: str = typer.Option("configs/default.yaml", "--config", "-c"),
    strategy: str = typer.Option(..., "--strategy", "-s"),
    poll_seconds: int = typer.Option(60, "--poll"),
):
    """Run a strategy in paper-trading mode against Alpaca paper."""
    cfg = load_config(config)
    if cfg.mode == "live":
        console.print("[red]Refusing to paper-run with mode=live in config.[/red]")
        raise typer.Exit(1)
    _setup_logging(cfg.monitoring.log_level, cfg.monitoring.log_file)
    asyncio.run(_paper_loop(cfg, strategy, poll_seconds))


@app.command()
def live(
    config: str = typer.Option(..., "--config", "-c"),
    strategy: str = typer.Option(..., "--strategy", "-s"),
    confirm: bool = typer.Option(False, "--i-have-validated-this-strategy-for-90-days"),
):
    """Live trading. Gated behind explicit flag; never the default."""
    if not confirm:
        console.print(
            "[red]Refusing to go live without --i-have-validated-this-strategy-for-90-days flag.[/red]"
        )
        raise typer.Exit(1)
    cfg = load_config(config)
    if cfg.mode != "live":
        console.print("[red]Config mode must be 'live' for live trading.[/red]")
        raise typer.Exit(1)
    _setup_logging(cfg.monitoring.log_level, cfg.monitoring.log_file)
    cfg.brokers.alpaca.paper = False
    asyncio.run(_paper_loop(cfg, strategy, 60))


async def _paper_loop(cfg: Config, strategy_name: str, poll_seconds: int):
    broker = AlpacaBroker(cfg.brokers.alpaca)
    await broker.connect()
    router = ExecutionRouter(broker, dry_run=False)
    risk = RiskManager(cfg.capital)

    strat_cfg = getattr(cfg.strategies, strategy_name)
    ctx = StrategyContext(
        params=strat_cfg.params,
        risk_pct_per_trade=cfg.capital.risk_per_trade_pct,
        max_position_pct=cfg.capital.max_position_pct,
    )
    strat = build_strategy(strategy_name, ctx)

    src = DataSource(cfg.data, cfg.brokers.alpaca)
    universe = list(strat_cfg.params.get("universe", []))
    bench = strat_cfg.params.get("benchmark", "SPY")
    if bench and bench not in universe:
        universe.append(bench)

    log = logging.getLogger("apex2.runner")
    log.info("paper loop started: strategy=%s universe=%s", strategy_name, universe)

    starting_equity = (await broker.get_account()).equity
    daily_anchor = datetime.utcnow().date()
    daily_start_equity = starting_equity

    try:
        while True:
            if not await broker.is_market_open():
                log.info("market closed, sleeping 5 min")
                await asyncio.sleep(300)
                continue

            now = datetime.utcnow()
            if now.date() != daily_anchor:
                daily_anchor = now.date()
                daily_start_equity = (await broker.get_account()).equity

            # Pull recent daily bars (last ~1 year) for indicators.
            start_d = (now - timedelta(days=400)).date()
            bars: dict[str, pd.DataFrame] = {}
            for sym in universe:
                try:
                    df = src.get_bars(sym, start_d, now.date(), timeframe="1d")
                    if not df.empty:
                        bars[sym] = df
                except Exception as e:
                    log.warning("data fetch %s failed: %s", sym, e)
            if not bars:
                await asyncio.sleep(poll_seconds)
                continue

            from .backtest.engine import BTPosition, BTState
            account, positions = await asyncio.gather(
                broker.get_account(), broker.get_positions()
            )
            bt_state = BTState(
                cash=account.cash,
                positions={
                    p.symbol: BTPosition(qty=p.qty, avg_price=p.avg_entry_price) for p in positions
                },
                last_close={
                    sym: float(df["close"].iloc[-1]) for sym, df in bars.items() if not df.empty
                },
            )
            ts = max(df.index.max() for df in bars.values())
            orders = strat.on_bar(bt_state, ts, bars) or []

            open_symbols = {p.symbol for p in positions if p.qty != 0}
            daily_pnl = account.equity - daily_start_equity

            for o in orders:
                px = float(bars[o.symbol].loc[ts, "close"]) if ts in bars[o.symbol].index else 0.0
                gate = GateInput(
                    equity=account.equity,
                    starting_equity=daily_start_equity,
                    open_symbols=open_symbols,
                    target_symbol=o.symbol,
                    notional=o.qty * px,
                    daily_pnl=daily_pnl,
                )
                ok, reason = risk.can_open(gate)
                if not ok and o.side == "buy":
                    log.warning("risk rejected %s %s: %s", o.side, o.symbol, reason)
                    continue
                req = ExecRequest(symbol=o.symbol, side=o.side, qty=o.qty, reason=o.reason)
                try:
                    await router.submit(req)
                except Exception as e:
                    log.error("submit failed %s %s: %s", o.side, o.symbol, e)

            await asyncio.sleep(poll_seconds)
    finally:
        await broker.disconnect()


def _print_analyzers(extras: dict) -> None:
    if not extras:
        return
    table = Table(title="Analyzers", show_header=True)
    table.add_column("Analyzer")
    table.add_column("Result")
    for name, value in extras.items():
        if isinstance(value, dict):
            value = ", ".join(f"{k}={v}" for k, v in value.items())
        table.add_row(name, str(value))
    console.print(table)


def _print_metrics(strategy: str, m, starting_cash: float, equity_curve) -> None:
    table = Table(title=f"Backtest results — {strategy}", show_header=True)
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    rows = [
        ("Starting equity", f"${starting_cash:,.0f}"),
        ("Ending equity", f"${equity_curve[-1][1]:,.0f}" if equity_curve else "n/a"),
        ("Total return", f"{m.total_return_pct:.2f}%"),
        ("CAGR", f"{m.cagr_pct:.2f}%"),
        ("Sharpe", f"{m.sharpe:.2f}"),
        ("Sortino", f"{m.sortino:.2f}"),
        ("Max drawdown", f"{m.max_drawdown_pct:.2f}%"),
        ("Calmar", f"{m.calmar:.2f}"),
        ("Win rate", f"{m.win_rate_pct:.2f}%"),
        ("Profit factor", f"{m.profit_factor:.2f}"),
        ("Trades", str(m.num_trades)),
        ("Avg trade return", f"{m.avg_trade_pct:.4f}%"),
        ("Exposure", f"{m.exposure_pct:.2f}%"),
    ]
    for k, v in rows:
        table.add_row(k, v)
    console.print(table)


if __name__ == "__main__":
    app()
