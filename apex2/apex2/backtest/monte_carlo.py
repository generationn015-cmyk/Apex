"""Monte Carlo trade resampling — what's the realistic worst case?

Approach (Pardo, "Evaluation and Optimization of Trading Strategies"):
  1. Take the trade-return series produced by the backtest.
  2. Resample with replacement N times to build N synthetic equity curves.
  3. Compute drawdown distribution → 5%, 50%, 95% percentiles.

This catches the question: "we got lucky on the order of trades — what if
the bad streaks had clustered?" It does NOT change the strategy's expected
Sharpe; it shows the dispersion of paths the strategy could plausibly produce.

Output: dict of percentiles of max-drawdown and final-return.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .engine import BTFill
from .metrics import _trade_pnls


@dataclass
class MonteCarloResult:
    n_simulations: int
    n_trades: int
    final_return_pct: dict[str, float]      # p05, p50, p95 of total return %
    max_dd_pct: dict[str, float]            # p05, p50, p95 of max DD %
    realized_max_dd_pct: float
    realized_return_pct: float


def monte_carlo_resample(
    fills: list[BTFill],
    n_simulations: int = 5000,
    seed: int = 42,
) -> MonteCarloResult:
    pnls = _trade_pnls(fills)
    if not pnls:
        return MonteCarloResult(
            n_simulations=0,
            n_trades=0,
            final_return_pct={"p05": 0, "p50": 0, "p95": 0},
            max_dd_pct={"p05": 0, "p50": 0, "p95": 0},
            realized_max_dd_pct=0,
            realized_return_pct=0,
        )

    rng = np.random.default_rng(seed)
    arr = np.array(pnls)
    n = len(arr)

    final_returns = np.zeros(n_simulations)
    max_dds = np.zeros(n_simulations)

    for i in range(n_simulations):
        idx = rng.integers(0, n, size=n)
        path = arr[idx]
        equity = np.cumprod(1.0 + path)
        final_returns[i] = equity[-1] - 1.0
        running_peak = np.maximum.accumulate(equity)
        dd = (equity - running_peak) / running_peak
        max_dds[i] = float(dd.min())

    realized_eq = np.cumprod(1.0 + arr)
    realized_peak = np.maximum.accumulate(realized_eq)
    realized_dd = float(((realized_eq - realized_peak) / realized_peak).min())
    realized_ret = float(realized_eq[-1] - 1.0)

    return MonteCarloResult(
        n_simulations=n_simulations,
        n_trades=n,
        final_return_pct={
            "p05": round(float(np.percentile(final_returns, 5)) * 100, 2),
            "p50": round(float(np.percentile(final_returns, 50)) * 100, 2),
            "p95": round(float(np.percentile(final_returns, 95)) * 100, 2),
        },
        max_dd_pct={
            "p05": round(float(np.percentile(max_dds, 5)) * 100, 2),
            "p50": round(float(np.percentile(max_dds, 50)) * 100, 2),
            "p95": round(float(np.percentile(max_dds, 95)) * 100, 2),
        },
        realized_max_dd_pct=round(realized_dd * 100, 2),
        realized_return_pct=round(realized_ret * 100, 2),
    )
