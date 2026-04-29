"""Tactical bond/equity rotation using yield curve slope.

Edge thesis (Campbell-Shiller / FRB research, 50+ years):
  - Inverted yield curve (10y - 2y < 0) precedes recession with high reliability.
  - Recession = equities underperform bonds.
  - Rotate to TLT (long bonds) when curve inverted; SPY when curve positive.
  - Smooth transitions to avoid whipsaw at the boundary.

Implementation:
  - Fetch FRED T10Y2Y series (cached locally).
  - 21-day SMA of slope as the regime signal.
  - Hysteresis: enter SPY when slope > +0.20%; switch to TLT when < -0.20%.
  - Hold full allocation in selected asset; equal weight if undecided.

Capacity: enormous (SPY/TLT are highest-volume ETFs).
Trade frequency: 2-6 rotations per year. Low cost.
"""
from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from ..backtest.engine import BTOrder, BTState
from .base import Strategy

log = logging.getLogger("apex2.strategy.bond_equity")


class BondEquityRotation(Strategy):
    name = "bond_equity_rotation"

    def __init__(self, ctx):
        super().__init__(ctx)
        p = ctx.params
        self.equity_ticker = p.get("equity_ticker", "SPY")
        self.bond_ticker = p.get("bond_ticker", "TLT")
        self.slope_sma = int(p.get("slope_sma_days", 21))
        self.enter_equity_threshold = float(p.get("enter_equity_threshold", 0.20))
        self.enter_bond_threshold = float(p.get("enter_bond_threshold", -0.20))
        self._slope_cache: pd.Series | None = None
        self._slope_cache_dt: date | None = None
        self._current_holding: str | None = None     # "equity" | "bond" | None

    def _slope_series(self, end: date) -> pd.Series:
        # Fetch once per session, then slice to <= end on each call.
        # FRED slope is a slow daily series — no need to refetch every bar.
        if self._slope_cache is None:
            try:
                from ..data.fred import yield_curve_slope
                self._slope_cache = yield_curve_slope(start=date(2010, 1, 1), end=date.today())
                self._slope_cache_dt = date.today()
            except Exception as e:
                log.warning("FRED slope fetch failed: %s", e)
                self._slope_cache = pd.Series(dtype=float)
                self._slope_cache_dt = date.today()
        if self._slope_cache.empty:
            return self._slope_cache
        return self._slope_cache.loc[self._slope_cache.index <= pd.Timestamp(end)]

    def on_bar(self, state: BTState, ts: pd.Timestamp, bars: dict[str, pd.DataFrame]):
        ts_date = ts.date() if hasattr(ts, "date") else date.today()
        slope = self._slope_series(ts_date)
        if slope.empty:
            return []
        slope = slope.loc[slope.index <= pd.Timestamp(ts_date)]
        if len(slope) < self.slope_sma + 5:
            return []
        slope_smooth = slope.rolling(self.slope_sma).mean().iloc[-1]
        if pd.isna(slope_smooth):
            return []

        # Decide regime with hysteresis.
        if slope_smooth >= self.enter_equity_threshold:
            target = "equity"
        elif slope_smooth <= self.enter_bond_threshold:
            target = "bond"
        else:
            target = self._current_holding or "equity"

        if target == self._current_holding:
            return []

        equity = state.mark_to_market(bars, ts)
        target_dollars = equity * (self.ctx.max_position_pct / 100.0)
        orders: list[BTOrder] = []

        # Liquidate the asset we're rotating out of.
        for sym in (self.equity_ticker, self.bond_ticker):
            pos = state.positions.get(sym)
            if pos and pos.qty > 0:
                orders.append(BTOrder(ts, sym, "sell", pos.qty, reason=f"rotate_to_{target}"))

        # Buy target.
        target_sym = self.equity_ticker if target == "equity" else self.bond_ticker
        df = self.history(bars, target_sym, ts)
        if df is None or df.empty:
            return orders
        px = float(df["close"].iloc[-1])
        qty = int(target_dollars // px)
        if qty > 0:
            orders.append(BTOrder(ts, target_sym, "buy", qty, reason=f"rotate_to_{target}_slope={slope_smooth:.2f}"))
            self._current_holding = target

        return orders
