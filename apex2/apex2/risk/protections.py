"""Pluggable protection guards (freqtrade IProtection pattern).

A protection inspects recent trading history and decides whether the bot is
allowed to open new positions. Each guard is independent and short-circuiting:
the first guard that says NO halts trading until its cooldown clears.

Wire into the runtime via `ProtectionChain.allow_open()` before risk sizing.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..backtest.engine import BTFill


@dataclass
class ProtectionContext:
    now: datetime
    fills: list[BTFill]
    equity: float
    starting_equity: float


class Protection(ABC):
    name: str = "base"

    @abstractmethod
    def check(self, ctx: ProtectionContext) -> tuple[bool, str]:
        """Return (allow, reason). allow=False blocks new entries."""


class CooldownAfterStop(Protection):
    """Block new entries for `cooldown_minutes` after any losing exit."""
    name = "cooldown_after_stop"

    def __init__(self, cooldown_minutes: int = 30):
        self.cooldown = timedelta(minutes=cooldown_minutes)

    def check(self, ctx):
        if not ctx.fills:
            return True, "no_history"
        last = ctx.fills[-1]
        if last.side != "sell":
            return True, "ok"
        last_dt = last.timestamp.to_pydatetime() if hasattr(last.timestamp, "to_pydatetime") else last.timestamp
        if (ctx.now - last_dt) < self.cooldown:
            return False, f"cooldown active until {last_dt + self.cooldown:%H:%M}"
        return True, "ok"


class MaxConsecutiveLosses(Protection):
    """Halt after N consecutive losing round-trips."""
    name = "max_consecutive_losses"

    def __init__(self, max_losses: int = 3):
        self.max_losses = max_losses

    def check(self, ctx):
        losses = 0
        last_entry_price: dict[str, float] = {}
        for f in ctx.fills:
            if f.side == "buy":
                last_entry_price[f.symbol] = f.price
            elif f.side == "sell" and f.symbol in last_entry_price:
                if f.price < last_entry_price[f.symbol]:
                    losses += 1
                else:
                    losses = 0
                last_entry_price.pop(f.symbol)
        if losses >= self.max_losses:
            return False, f"{losses} consecutive losses"
        return True, "ok"


class MaxDrawdownHalt(Protection):
    """Halt new entries once equity drops below threshold from starting equity."""
    name = "max_drawdown_halt"

    def __init__(self, max_dd_pct: float = 15.0):
        self.max_dd_pct = max_dd_pct

    def check(self, ctx):
        if ctx.starting_equity <= 0:
            return True, "no_baseline"
        dd_pct = (ctx.equity - ctx.starting_equity) / ctx.starting_equity * 100.0
        if dd_pct <= -self.max_dd_pct:
            return False, f"drawdown {dd_pct:.2f}% breached -{self.max_dd_pct}%"
        return True, "ok"


class ProtectionChain:
    """Evaluate guards in order. First failure short-circuits."""

    def __init__(self, protections: list[Protection]):
        self.protections = protections

    def allow_open(self, ctx: ProtectionContext) -> tuple[bool, str]:
        for p in self.protections:
            ok, reason = p.check(ctx)
            if not ok:
                return False, f"{p.name}: {reason}"
        return True, "ok"

    @classmethod
    def default(cls) -> "ProtectionChain":
        return cls([
            MaxDrawdownHalt(max_dd_pct=15.0),
            MaxConsecutiveLosses(max_losses=3),
            CooldownAfterStop(cooldown_minutes=30),
        ])
