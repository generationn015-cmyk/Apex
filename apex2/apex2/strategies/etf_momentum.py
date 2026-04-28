"""Cross-sectional ETF momentum.

Edge thesis: 6-month price momentum (skipping the most recent month) predicts
relative future returns. Replicated across decades (Jegadeesh & Titman 1993,
Asness/Moskowitz/Pedersen 2013). Capacity is enormous in liquid ETFs.

Rules:
  - Universe: liquid sector / asset-class ETFs.
  - Each rebalance day (default ~21 trading days):
      * Compute (close_T-skip / close_T-skip-lookback) - 1 for every symbol.
      * Optional absolute-momentum filter: only hold if SPY 6m return > 0.
      * Hold equal-weight top_n.
      * Liquidate anything not in the new top_n.
"""
from __future__ import annotations

import logging
from typing import Iterable

import pandas as pd

from ..backtest.engine import BTOrder, BTState
from ..indicators.features import momentum
from .base import Strategy

log = logging.getLogger("apex2.strategy.etf_momentum")


class ETFMomentum(Strategy):
    name = "etf_momentum"

    def __init__(self, ctx):
        super().__init__(ctx)
        p = ctx.params
        self.universe: list[str] = list(p.get("universe", []))
        self.lookback = int(p.get("lookback_days", 126))
        self.skip = int(p.get("skip_days", 21))
        self.top_n = int(p.get("top_n", 3))
        self.rebalance_days = int(p.get("rebalance_days", 21))
        self.abs_mom_filter = bool(p.get("abs_momentum_filter", True))
        self.bench = p.get("benchmark", "SPY")
        self._last_rebalance: pd.Timestamp | None = None

    def on_bar(self, state: BTState, ts: pd.Timestamp, bars: dict[str, pd.DataFrame]):
        if self._last_rebalance is not None:
            days = (ts - self._last_rebalance).days
            if days < self.rebalance_days:
                return []
        bench_df = self.history(bars, self.bench, ts)
        if bench_df is None or bench_df.empty:
            return []

        scores = self._score(bars, ts)
        if not scores:
            return []

        if self.abs_mom_filter:
            bench_mom = momentum(bench_df["close"], self.lookback, self.skip)
            if bench_mom.empty or pd.isna(bench_mom.iloc[-1]) or bench_mom.iloc[-1] <= 0:
                return list(self._liquidate_all(state, ts))

        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        winners = [s for s, _ in ranked[: self.top_n]]

        equity = state.mark_to_market(bars, ts)
        target_weight = 1.0 / max(len(winners), 1)
        target_dollars = equity * target_weight

        orders: list[BTOrder] = []
        # Liquidate non-winners.
        for sym, pos in list(state.positions.items()):
            if pos.qty != 0 and sym not in winners:
                orders.append(BTOrder(ts, sym, "sell", pos.qty, reason="exit_rebalance"))

        # Resize winners.
        for sym in winners:
            df = bars.get(sym)
            if df is None or ts not in df.index:
                continue
            px = float(df.loc[ts, "close"])
            if px <= 0:
                continue
            target_qty = int(target_dollars // px)
            current = state.positions.get(sym)
            current_qty = int(current.qty) if current else 0
            delta = target_qty - current_qty
            if delta > 0:
                orders.append(BTOrder(ts, sym, "buy", delta, reason="rebalance_in"))
            elif delta < 0:
                orders.append(BTOrder(ts, sym, "sell", -delta, reason="rebalance_out"))

        self._last_rebalance = ts
        return orders

    def _score(self, bars: dict[str, pd.DataFrame], ts: pd.Timestamp) -> dict[str, float]:
        out: dict[str, float] = {}
        for sym in self.universe:
            df = self.history(bars, sym, ts)
            if df is None or len(df) < self.lookback + self.skip + 1:
                continue
            mom = momentum(df["close"], self.lookback, self.skip)
            v = mom.iloc[-1]
            if not pd.isna(v):
                out[sym] = float(v)
        return out

    def _liquidate_all(self, state: BTState, ts: pd.Timestamp) -> Iterable[BTOrder]:
        for sym, pos in state.positions.items():
            if pos.qty > 0:
                yield BTOrder(ts, sym, "sell", pos.qty, reason="risk_off")
