"""Donchian channel breakout trend follower (turtle-style, simplified).

Edge thesis: persistent trends in macro asset classes (equities, bonds, gold,
oil, USD). Decades of CTA evidence. Profits from the fat right tail; many small
losses, occasional large wins. Crisis alpha (often profitable in 2008, 2020).

Rules:
  - Long-only on a small basket of liquid macro ETFs.
  - Entry: close breaks above N-day high (default 55).
  - Exit: close breaks below M-day low (default 20).
  - Risk per trade sized via ATR (atr_risk_mult ATRs of risk).
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ..backtest.engine import BTOrder, BTState
from ..indicators.features import atr, donchian
from .base import Strategy


@dataclass
class _Trade:
    entry_price: float


class DonchianTrend(Strategy):
    name = "donchian_trend"

    def __init__(self, ctx):
        super().__init__(ctx)
        p = ctx.params
        self.universe: list[str] = list(p.get("universe", []))
        self.entry_lookback = int(p.get("entry_lookback", 55))
        self.exit_lookback = int(p.get("exit_lookback", 20))
        self.atr_period = int(p.get("atr_period", 20))
        self.atr_risk_mult = float(p.get("atr_risk_mult", 2.0))
        self._open: dict[str, _Trade] = {}

    def on_bar(self, state: BTState, ts: pd.Timestamp, bars: dict[str, pd.DataFrame]):
        orders: list[BTOrder] = []
        equity = state.mark_to_market(bars, ts)
        risk_dollars = equity * (self.ctx.risk_pct_per_trade / 100.0)

        for sym in self.universe:
            df = self.history(bars, sym, ts)
            min_bars = max(self.entry_lookback, self.exit_lookback, self.atr_period) + 2
            if df is None or len(df) < min_bars:
                continue
            high = df["high"]
            low = df["low"]
            close = df["close"]

            # Use channel up to PRIOR bar to avoid look-ahead.
            entry_upper, _ = donchian(high.shift(1), low.shift(1), self.entry_lookback)
            _, exit_lower = donchian(high.shift(1), low.shift(1), self.exit_lookback)
            a = atr(high, low, close, self.atr_period)
            if pd.isna(entry_upper.iloc[-1]) or pd.isna(exit_lower.iloc[-1]) or pd.isna(a.iloc[-1]):
                continue
            px = float(close.iloc[-1])
            atr_v = float(a.iloc[-1])

            pos = state.positions.get(sym)
            held = pos and pos.qty > 0

            # Exit check first.
            if held and px < float(exit_lower.iloc[-1]):
                orders.append(BTOrder(ts, sym, "sell", pos.qty, reason="trend_exit"))
                self._open.pop(sym, None)
                continue

            # Entry check.
            if not held and px > float(entry_upper.iloc[-1]) and atr_v > 0:
                stop_distance = self.atr_risk_mult * atr_v
                qty = int(risk_dollars // stop_distance) if stop_distance > 0 else 0
                # Cap by max position pct as well.
                max_qty = int((equity * (self.ctx.max_position_pct / 100.0)) // px)
                qty = min(qty, max_qty)
                if qty > 0:
                    self._open[sym] = _Trade(entry_price=px)
                    orders.append(BTOrder(ts, sym, "buy", qty, reason="trend_entry"))

        return orders
