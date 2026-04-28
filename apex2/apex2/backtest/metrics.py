"""Performance metrics for backtest equity curves and fills."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .engine import BTFill


@dataclass
class Metrics:
    total_return_pct: float
    cagr_pct: float
    sharpe: float
    sortino: float
    max_drawdown_pct: float
    calmar: float
    win_rate_pct: float
    profit_factor: float
    num_trades: int
    avg_trade_pct: float
    exposure_pct: float


def compute_metrics(
    equity_curve: list[tuple[pd.Timestamp, float]],
    fills: list[BTFill],
    bars_per_year: int = 252,
) -> Metrics:
    if not equity_curve:
        return Metrics(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

    eq = pd.Series({ts: v for ts, v in equity_curve}).sort_index()
    rets = eq.pct_change().dropna()
    if len(rets) == 0:
        return Metrics(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

    initial = float(eq.iloc[0])
    final = float(eq.iloc[-1])
    total_return = (final / initial) - 1.0

    years = max(len(rets) / bars_per_year, 1e-9)
    cagr = (final / initial) ** (1 / years) - 1.0 if initial > 0 else 0.0

    std = rets.std(ddof=0)
    sharpe = (rets.mean() / std) * np.sqrt(bars_per_year) if std > 0 else 0.0
    downside = rets[rets < 0].std(ddof=0)
    sortino = (rets.mean() / downside) * np.sqrt(bars_per_year) if downside > 0 else 0.0

    cum = eq / eq.cummax()
    max_dd = float((cum - 1.0).min())
    calmar = cagr / abs(max_dd) if max_dd < 0 else 0.0

    trade_pnls = _trade_pnls(fills)
    if trade_pnls:
        wins = [p for p in trade_pnls if p > 0]
        losses = [p for p in trade_pnls if p < 0]
        win_rate = len(wins) / len(trade_pnls)
        profit_factor = (
            sum(wins) / abs(sum(losses)) if losses else float("inf") if wins else 0.0
        )
        avg_trade = float(np.mean(trade_pnls))
    else:
        win_rate = profit_factor = avg_trade = 0.0

    bars_in_market = (rets != 0).sum()
    exposure = bars_in_market / len(rets) if len(rets) > 0 else 0.0

    return Metrics(
        total_return_pct=round(total_return * 100, 2),
        cagr_pct=round(cagr * 100, 2),
        sharpe=round(float(sharpe), 2),
        sortino=round(float(sortino), 2),
        max_drawdown_pct=round(max_dd * 100, 2),
        calmar=round(float(calmar), 2),
        win_rate_pct=round(win_rate * 100, 2),
        profit_factor=round(float(profit_factor), 2),
        num_trades=len(trade_pnls),
        avg_trade_pct=round(avg_trade * 100, 4),
        exposure_pct=round(exposure * 100, 2),
    )


def _trade_pnls(fills: list[BTFill]) -> list[float]:
    """Pair entry/exit fills per symbol FIFO; emit pct return per round-trip."""
    by_sym: dict[str, list[BTFill]] = {}
    for f in fills:
        by_sym.setdefault(f.symbol, []).append(f)
    pnls = []
    for sym_fills in by_sym.values():
        position_qty = 0.0
        avg_entry = 0.0
        for f in sym_fills:
            signed = f.qty if f.side == "buy" else -f.qty
            new_qty = position_qty + signed
            if position_qty == 0:
                avg_entry = f.price
            elif (position_qty > 0 and signed > 0) or (position_qty < 0 and signed < 0):
                avg_entry = (avg_entry * position_qty + f.price * signed) / new_qty
            elif new_qty == 0 or (position_qty > 0) != (new_qty > 0):
                # Closed (or flipped) — record pct return.
                if avg_entry > 0:
                    direction = 1 if position_qty > 0 else -1
                    pnls.append(direction * (f.price - avg_entry) / avg_entry)
                avg_entry = f.price if new_qty != 0 else 0.0
            position_qty = new_qty
    return pnls
