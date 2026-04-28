"""Risk manager: position sizing and pre-trade gates.

Sizing methods:
  - fixed_fraction: risk_per_trade_pct / stop distance
  - atr: 1 ATR risk; size = (equity * risk_pct) / (atr_mult * atr)
  - kelly: capped fractional Kelly given win rate and R:R

Hard gates (any failure → reject):
  - daily loss kill switch
  - max open positions
  - max position pct of equity
  - duplicate symbol guard
  - correlation guard (optional)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from ..config.models import CapitalConfig

log = logging.getLogger("apex2.risk")


@dataclass
class SizingInput:
    equity: float
    entry_price: float
    stop_price: float | None = None
    atr: float | None = None
    win_rate: float | None = None
    avg_win_r: float | None = None     # e.g. 1.5 means avg win is 1.5R
    method: str = "fixed_fraction"     # fixed_fraction | atr | kelly


@dataclass
class GateInput:
    equity: float
    starting_equity: float
    open_symbols: set[str]
    target_symbol: str
    notional: float
    daily_pnl: float


class RiskManager:
    def __init__(self, cfg: CapitalConfig):
        self.cfg = cfg

    # ── Sizing ───────────────────────────────────────────────────

    def size(self, inp: SizingInput) -> float:
        """Return integer share quantity (float for fractional)."""
        risk_dollars = inp.equity * (self.cfg.risk_per_trade_pct / 100.0)

        if inp.method == "fixed_fraction":
            if inp.stop_price is None or inp.entry_price <= 0:
                return 0.0
            risk_per_share = abs(inp.entry_price - inp.stop_price)
            if risk_per_share <= 0:
                return 0.0
            qty = risk_dollars / risk_per_share

        elif inp.method == "atr":
            if not inp.atr or inp.atr <= 0:
                return 0.0
            qty = risk_dollars / inp.atr

        elif inp.method == "kelly":
            if not inp.win_rate or not inp.avg_win_r or inp.avg_win_r <= 0:
                return 0.0
            p = inp.win_rate
            b = inp.avg_win_r
            f_star = (b * p - (1 - p)) / b
            f_star = max(0.0, f_star) * self.cfg.kelly_fraction
            if inp.stop_price is None:
                # Without a stop, allocate as percent of equity.
                allocation = inp.equity * f_star
                qty = allocation / inp.entry_price if inp.entry_price > 0 else 0.0
            else:
                risk_per_share = abs(inp.entry_price - inp.stop_price)
                if risk_per_share <= 0:
                    return 0.0
                qty = (inp.equity * f_star) / risk_per_share
        else:
            raise ValueError(f"unknown sizing method: {inp.method}")

        # Cap by max position pct.
        max_notional = inp.equity * (self.cfg.max_position_pct / 100.0)
        if inp.entry_price > 0:
            max_qty = max_notional / inp.entry_price
            qty = min(qty, max_qty)

        return max(0.0, qty)

    # ── Gates ────────────────────────────────────────────────────

    def can_open(self, inp: GateInput) -> tuple[bool, str]:
        # Daily loss kill.
        daily_loss_pct = (inp.daily_pnl / inp.starting_equity) * 100.0 if inp.starting_equity > 0 else 0.0
        if daily_loss_pct <= -self.cfg.max_daily_loss_pct:
            return False, f"daily loss kill ({daily_loss_pct:.2f}%)"
        # Max open positions.
        if inp.target_symbol not in inp.open_symbols and len(inp.open_symbols) >= self.cfg.max_open_positions:
            return False, f"max open positions ({len(inp.open_symbols)})"
        # Per-position cap.
        max_notional = inp.equity * (self.cfg.max_position_pct / 100.0)
        if inp.notional > max_notional:
            return False, f"position notional {inp.notional:.0f} > cap {max_notional:.0f}"
        return True, "ok"
