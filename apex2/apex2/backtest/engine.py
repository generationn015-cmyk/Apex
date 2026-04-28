"""Event-driven backtest engine.

Design rules:
  - Strategies see only bars with timestamp <= current bar (no look-ahead).
  - Signals emitted at bar T fill at the OPEN of bar T+1 by default ("next_open"),
    or CLOSE of T (with caveat) or midpoint of T+1 H/L.
  - Fees: per-share + per-trade.
  - Slippage: bps of fill price, applied adversely (+ for buys, - for sells).
  - Partial fills: bar volume cap optional (skipped by default; equities are deep).
  - Equity curve recorded at bar close mark-to-market.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

import pandas as pd

from ..config.models import BacktestConfig

log = logging.getLogger("apex2.backtest")


@dataclass
class BTOrder:
    timestamp: pd.Timestamp
    symbol: str
    side: str          # "buy" or "sell"
    qty: float
    reason: str = ""   # e.g. "entry", "stop", "exit", "rebalance"


@dataclass
class BTFill:
    timestamp: pd.Timestamp
    symbol: str
    side: str
    qty: float
    price: float
    commission: float
    slippage: float


@dataclass
class BTPosition:
    qty: float = 0.0
    avg_price: float = 0.0


@dataclass
class BTState:
    cash: float
    positions: dict[str, BTPosition] = field(default_factory=dict)
    fills: list[BTFill] = field(default_factory=list)
    equity_curve: list[tuple[pd.Timestamp, float]] = field(default_factory=list)
    pending_orders: list[BTOrder] = field(default_factory=list)
    last_close: dict[str, float] = field(default_factory=dict)

    def mark_to_market(self, bars: dict[str, pd.DataFrame] | None = None, ts: pd.Timestamp | None = None) -> float:
        """Equity = cash + sum(qty * last_known_close).

        Live mode passes None for bars/ts and relies on `last_close` having been
        updated externally. Backtest engine populates `last_close` per bar.
        """
        equity = self.cash
        for sym, pos in self.positions.items():
            if pos.qty == 0:
                continue
            px = self.last_close.get(sym)
            if px is None and bars is not None and ts is not None:
                df = bars.get(sym)
                if df is not None and ts in df.index:
                    px = float(df.loc[ts, "close"])
            if px is not None:
                equity += pos.qty * px
        return equity


# Strategy callable: (state, ts, bars) → orders. `bars` is the full historical
# frame per symbol; strategies slice via `.loc[:ts]` to respect look-ahead.
StrategyFn = Callable[[BTState, pd.Timestamp, dict[str, pd.DataFrame]], list[BTOrder]]


class BacktestEngine:
    def __init__(self, cfg: BacktestConfig):
        self.cfg = cfg

    def run(
        self,
        bars_by_symbol: dict[str, pd.DataFrame],
        strategy: StrategyFn,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> BTState:
        # Build a unified, sorted timeline of bar timestamps.
        all_ts = sorted(set().union(*(df.index for df in bars_by_symbol.values())))
        if start is not None:
            all_ts = [t for t in all_ts if t >= pd.Timestamp(start)]
        if end is not None:
            all_ts = [t for t in all_ts if t <= pd.Timestamp(end)]

        state = BTState(cash=self.cfg.initial_cash)

        for ts in all_ts:
            # Fill orders queued from previous bar at this bar's open (next_open model).
            self._process_pending(state, ts, bars_by_symbol)

            # Update last_close cache so strategies and mark-to-market avoid index scans.
            for sym, df in bars_by_symbol.items():
                if ts in df.index:
                    state.last_close[sym] = float(df.loc[ts, "close"])

            # Strategy operates on the full bars dict; it slices via `.loc[:ts]` itself.
            new_orders = strategy(state, ts, bars_by_symbol) or []
            for o in new_orders:
                state.pending_orders.append(o)

            state.equity_curve.append((ts, state.mark_to_market()))

        return state

    def _process_pending(
        self,
        state: BTState,
        ts: pd.Timestamp,
        bars_by_symbol: dict[str, pd.DataFrame],
    ) -> None:
        if not state.pending_orders:
            return
        still_pending = []
        for order in state.pending_orders:
            df = bars_by_symbol.get(order.symbol)
            if df is None or ts not in df.index:
                still_pending.append(order)
                continue
            bar = df.loc[ts]
            fill_price = self._fill_price(bar)
            slip = fill_price * (self.cfg.slippage_bps / 10_000.0)
            if order.side == "buy":
                exec_price = fill_price + slip
            else:
                exec_price = fill_price - slip
            commission = (
                self.cfg.commission_per_share * abs(order.qty) + self.cfg.commission_per_trade
            )
            self._apply_fill(state, ts, order, exec_price, commission, slip)
        state.pending_orders = still_pending

    def _fill_price(self, bar: pd.Series) -> float:
        model = self.cfg.fill_model
        if model == "next_open":
            return float(bar["open"])
        if model == "close":
            return float(bar["close"])
        if model == "midpoint":
            return (float(bar["high"]) + float(bar["low"])) / 2.0
        return float(bar["open"])

    def _apply_fill(
        self,
        state: BTState,
        ts: pd.Timestamp,
        order: BTOrder,
        price: float,
        commission: float,
        slippage: float,
    ) -> None:
        pos = state.positions.setdefault(order.symbol, BTPosition())
        signed_qty = order.qty if order.side == "buy" else -order.qty

        # Update avg price for adds in same direction; reduce/flip otherwise.
        new_qty = pos.qty + signed_qty
        if pos.qty == 0 or (pos.qty > 0 and signed_qty > 0) or (pos.qty < 0 and signed_qty < 0):
            total_cost = pos.qty * pos.avg_price + signed_qty * price
            pos.avg_price = total_cost / new_qty if new_qty != 0 else 0.0
        elif new_qty == 0:
            pos.avg_price = 0.0
        elif (pos.qty > 0 and new_qty > 0) or (pos.qty < 0 and new_qty < 0):
            pass  # partial close, keep avg
        else:
            pos.avg_price = price  # flipped direction
        pos.qty = new_qty

        state.cash -= signed_qty * price + commission
        state.fills.append(
            BTFill(
                timestamp=ts,
                symbol=order.symbol,
                side=order.side,
                qty=order.qty,
                price=price,
                commission=commission,
                slippage=slippage,
            )
        )

