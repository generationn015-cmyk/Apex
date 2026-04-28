"""Backtest engine sanity tests."""
from __future__ import annotations

import numpy as np
import pandas as pd

from apex2.backtest.engine import BacktestEngine, BTOrder, BTState
from apex2.backtest.metrics import compute_metrics
from apex2.config.models import BacktestConfig


def _make_bars(n: int = 100, start_price: float = 100.0, drift: float = 0.001) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    rets = rng.normal(drift, 0.01, size=n)
    closes = start_price * np.cumprod(1 + rets)
    idx = pd.date_range("2024-01-02", periods=n, freq="B")
    df = pd.DataFrame(
        {
            "open": closes,
            "high": closes * 1.005,
            "low": closes * 0.995,
            "close": closes,
            "volume": 1_000_000,
        },
        index=idx,
    )
    return df


def test_engine_no_lookahead_buy_and_hold():
    """Order emitted on day i fills at day i+1 open. Equity at day 0 == cash."""
    bars = {"AAA": _make_bars(20)}

    def strategy(state: BTState, ts: pd.Timestamp, snap):
        if not state.positions and not state.pending_orders:
            return [BTOrder(ts, "AAA", "buy", 10, reason="entry")]
        return []

    cfg = BacktestConfig(initial_cash=10_000, slippage_bps=0)
    engine = BacktestEngine(cfg)
    state = engine.run(bars, strategy)

    # First fill should be at the OPEN of bar 1 (second bar), not bar 0.
    assert state.fills, "expected at least one fill"
    first_fill = state.fills[0]
    assert first_fill.timestamp == bars["AAA"].index[1]
    assert first_fill.price == bars["AAA"].iloc[1]["open"]


def test_engine_slippage_is_adverse():
    bars = {"AAA": _make_bars(5)}

    def strategy(state, ts, snap):
        if not state.positions and not state.pending_orders:
            return [BTOrder(ts, "AAA", "buy", 1, reason="entry")]
        return []

    cfg_clean = BacktestConfig(initial_cash=1000, slippage_bps=0)
    cfg_slipped = BacktestConfig(initial_cash=1000, slippage_bps=50)  # 0.50%

    state_clean = BacktestEngine(cfg_clean).run(bars, strategy)
    state_slipped = BacktestEngine(cfg_slipped).run(bars, strategy)
    assert state_slipped.fills[0].price > state_clean.fills[0].price


def test_metrics_sane_on_buy_and_hold():
    bars = {"AAA": _make_bars(252, drift=0.0006)}  # ~ +15% drift over a year

    def strategy(state, ts, snap):
        if not state.positions and not state.pending_orders:
            return [BTOrder(ts, "AAA", "buy", 10, reason="entry")]
        return []

    cfg = BacktestConfig(initial_cash=10_000, slippage_bps=0)
    state = BacktestEngine(cfg).run(bars, strategy)
    m = compute_metrics(state.equity_curve, state.fills)
    # No round trips in pure buy-and-hold so trades=0 is acceptable.
    assert m.total_return_pct != 0
    assert -100 <= m.max_drawdown_pct <= 0
