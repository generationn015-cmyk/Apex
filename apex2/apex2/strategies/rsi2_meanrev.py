"""RSI(2) mean reversion (Larry Connors-style) with regime + ATR stops.

Edge thesis: short-horizon overreaction in liquid US equities. RSI(2)<10 in a
bull regime (price > 200d SMA) tends to mean-revert within a few days.

Rules:
  - Long-only.
  - Regime filter: close > regime_sma (default 200d).
  - Entry: RSI(2) < rsi_oversold AND no current position.
  - Exit: RSI(2) > rsi_exit OR price closes below ATR stop OR 10 trading days held.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ..backtest.engine import BTOrder, BTState
from ..indicators.features import atr, rsi, sma
from .base import Strategy


@dataclass
class _OpenTrade:
    entry_ts: pd.Timestamp
    entry_price: float
    stop_price: float
    bars_held: int = 0


class RSI2MeanReversion(Strategy):
    name = "rsi2_meanrev"

    def __init__(self, ctx):
        super().__init__(ctx)
        p = ctx.params
        self.universe: list[str] = list(p.get("universe", []))
        self.rsi_period = int(p.get("rsi_period", 2))
        self.rsi_oversold = float(p.get("rsi_oversold", 10))
        self.rsi_exit = float(p.get("rsi_exit", 70))
        self.regime_sma = int(p.get("regime_sma", 200))
        self.atr_period = int(p.get("atr_period", 14))
        self.atr_stop_mult = float(p.get("atr_stop_mult", 2.5))
        self.max_hold_bars = int(p.get("max_hold_bars", 10))
        self._open: dict[str, _OpenTrade] = {}

    def on_bar(self, state: BTState, ts: pd.Timestamp, bars: dict[str, pd.DataFrame]):
        orders: list[BTOrder] = []

        equity = state.mark_to_market(bars, ts)
        per_position_dollars = equity * (self.ctx.max_position_pct / 100.0)

        for sym in self.universe:
            df = self.history(bars, sym, ts)
            if df is None or len(df) < max(self.regime_sma, self.atr_period, self.rsi_period) + 2:
                continue
            close = df["close"]
            r = rsi(close, self.rsi_period).iloc[-1]
            ma = sma(close, self.regime_sma).iloc[-1]
            a = atr(df["high"], df["low"], close, self.atr_period).iloc[-1]
            if pd.isna(r) or pd.isna(ma) or pd.isna(a):
                continue
            px = float(close.iloc[-1])

            pos = state.positions.get(sym)
            held = pos and pos.qty > 0
            open_trade = self._open.get(sym)

            if held and open_trade is not None:
                open_trade.bars_held += 1
                hit_stop = px <= open_trade.stop_price
                hit_target = r > self.rsi_exit
                aged_out = open_trade.bars_held >= self.max_hold_bars
                if hit_stop or hit_target or aged_out:
                    orders.append(
                        BTOrder(
                            ts, sym, "sell", pos.qty,
                            reason="stop" if hit_stop else "target" if hit_target else "time_exit",
                        )
                    )
                    self._open.pop(sym, None)
                continue

            # Entry.
            if not held and r < self.rsi_oversold and px > ma and px > 0:
                qty = int(per_position_dollars // px)
                if qty <= 0:
                    continue
                stop = px - self.atr_stop_mult * float(a)
                self._open[sym] = _OpenTrade(entry_ts=ts, entry_price=px, stop_price=stop)
                orders.append(BTOrder(ts, sym, "buy", qty, reason="entry"))

        return orders
