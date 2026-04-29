"""Defensive momentum — own the most stable trending assets.

Edge thesis (Frazzini-Pedersen "Betting Against Beta", Asness "Quality Minus Junk"):
  - Risk-adjusted returns are higher for low-vol assets.
  - Combining momentum (12m total return) with low volatility (60d realized vol)
    gives a "smart" momentum tilt that avoids hot but fragile names.

Strategy:
  - Universe: defensive sector ETFs + factor ETFs (USMV, SPLV, XLV, XLP, etc.)
  - Score = momentum_12m / realized_vol_60d. Higher = better risk-adj momentum.
  - Hold top-K equal-weight, monthly rebalance.
  - Cash filter: require benchmark (SPY) > 200d SMA to be invested at all.

Why this differs from etf_momentum:
  - The disqualified etf_momentum used raw 12-1 month return on a broad set.
  - This version normalizes by volatility AND uses a defensive universe.
  - Lower drawdown profile, smoother equity curve.
"""
from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

from ..backtest.engine import BTOrder, BTState
from ..indicators.features import sma
from .base import Strategy


class DefensiveMomentum(Strategy):
    name = "defensive_momentum"

    def __init__(self, ctx):
        super().__init__(ctx)
        p = ctx.params
        self.universe: list[str] = list(p.get(
            "universe",
            ["USMV", "SPLV", "XLV", "XLP", "XLU", "VIG", "QUAL", "MTUM"]
        ))
        self.benchmark = p.get("benchmark", "SPY")
        self.regime_sma = int(p.get("regime_sma", 200))
        self.mom_lookback = int(p.get("momentum_lookback", 252))
        self.mom_skip = int(p.get("momentum_skip", 21))
        self.vol_window = int(p.get("vol_window", 60))
        self.top_k = int(p.get("top_k", 3))
        self.rebalance_days = int(p.get("rebalance_days", 21))
        self._last_rebalance: pd.Timestamp | None = None

    def _score(self, df: pd.DataFrame) -> float | None:
        if len(df) < self.mom_lookback + self.mom_skip + 5:
            return None
        close = df["close"]
        end_px = close.shift(self.mom_skip).iloc[-1]
        start_px = close.shift(self.mom_skip + self.mom_lookback).iloc[-1]
        if pd.isna(end_px) or pd.isna(start_px) or start_px <= 0:
            return None
        mom = float(end_px / start_px - 1.0)
        rets = close.pct_change().tail(self.vol_window)
        vol = float(rets.std(ddof=0)) * np.sqrt(252)
        if not np.isfinite(vol) or vol <= 0:
            return None
        return mom / vol

    def on_bar(self, state: BTState, ts: pd.Timestamp, bars: dict[str, pd.DataFrame]):
        if self._last_rebalance is not None:
            days = (ts - self._last_rebalance).days
            if days < self.rebalance_days:
                return []

        bench_df = self.history(bars, self.benchmark, ts)
        if bench_df is None or len(bench_df) < self.regime_sma:
            return []

        bench_sma = sma(bench_df["close"], self.regime_sma).iloc[-1]
        bench_close = float(bench_df["close"].iloc[-1])
        risk_off = pd.isna(bench_sma) or bench_close < float(bench_sma)
        self._last_rebalance = ts

        if risk_off:
            return list(self._liquidate_all(state, ts))

        scores: dict[str, float] = {}
        for sym in self.universe:
            df = self.history(bars, sym, ts)
            if df is None:
                continue
            s = self._score(df)
            if s is not None and np.isfinite(s):
                scores[sym] = s

        if not scores:
            return []
        winners = [s for s, _ in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[: self.top_k]]
        equity = state.mark_to_market(bars, ts)
        target_per = equity * (self.ctx.max_position_pct / 100.0) / max(len(winners), 1)

        orders: list[BTOrder] = []
        # Sell anything not in winners.
        for sym, pos in list(state.positions.items()):
            if pos.qty > 0 and sym not in winners:
                orders.append(BTOrder(ts, sym, "sell", pos.qty, reason="defmom_exit"))

        for sym in winners:
            df = self.history(bars, sym, ts)
            if df is None:
                continue
            px = float(df["close"].iloc[-1])
            if px <= 0:
                continue
            target_qty = int(target_per // px)
            current = state.positions.get(sym)
            current_qty = int(current.qty) if current else 0
            delta = target_qty - current_qty
            if delta > 0:
                orders.append(BTOrder(ts, sym, "buy", delta, reason="defmom_in"))
            elif delta < 0:
                orders.append(BTOrder(ts, sym, "sell", -delta, reason="defmom_trim"))
        return orders

    def _liquidate_all(self, state: BTState, ts: pd.Timestamp) -> Iterable[BTOrder]:
        for sym, pos in state.positions.items():
            if pos.qty > 0:
                yield BTOrder(ts, sym, "sell", pos.qty, reason="defmom_risk_off")
