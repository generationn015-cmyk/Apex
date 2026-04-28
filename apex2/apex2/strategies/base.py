"""Base strategy class. Concrete strategies emit BTOrders given current state and bars."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd

from ..backtest.engine import BTOrder, BTState


@dataclass
class StrategyContext:
    """Anything strategies need beyond bars + state (configs, risk, etc.)."""
    params: dict
    risk_pct_per_trade: float = 1.0
    max_position_pct: float = 20.0


class Strategy(ABC):
    name: str = "base"

    def __init__(self, ctx: StrategyContext):
        self.ctx = ctx

    @abstractmethod
    def on_bar(
        self,
        state: BTState,
        ts: pd.Timestamp,
        bars: dict[str, pd.DataFrame],
    ) -> list[BTOrder]:
        """Called once per bar. Return list of orders to queue for next bar's open.

        `bars` contains the full historical DataFrame per symbol — strategies
        MUST slice to `<= ts` (e.g. via `df.loc[:ts]`) to avoid look-ahead.
        Use `history()` for the standard slice.
        """

    @staticmethod
    def history(bars: dict[str, pd.DataFrame], symbol: str, ts: pd.Timestamp) -> pd.DataFrame | None:
        """Return df.loc[:ts] for the symbol, or None if the symbol/bar is unavailable."""
        df = bars.get(symbol)
        if df is None or df.index.min() > ts:
            return None
        return df.loc[:ts]

    def __call__(self, state: BTState, ts: pd.Timestamp, bars: dict[str, pd.DataFrame]):
        return self.on_bar(state, ts, bars)
