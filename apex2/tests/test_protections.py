"""Protection chain tests."""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from apex2.backtest.engine import BTFill
from apex2.risk.protections import (CooldownAfterStop, MaxConsecutiveLosses,
                                    MaxDrawdownHalt, ProtectionChain,
                                    ProtectionContext)


def _ctx(now=None, fills=None, equity=10_000, starting=10_000):
    return ProtectionContext(
        now=now or datetime(2025, 1, 1, 12, 0),
        fills=fills or [],
        equity=equity,
        starting_equity=starting,
    )


def _fill(side, price, ts):
    return BTFill(timestamp=pd.Timestamp(ts), symbol="X", side=side, qty=1,
                  price=price, commission=0, slippage=0)


def test_cooldown_blocks_within_window():
    p = CooldownAfterStop(cooldown_minutes=30)
    sell_ts = datetime(2025, 1, 1, 11, 50)
    ok, _ = p.check(_ctx(now=datetime(2025, 1, 1, 12, 0), fills=[_fill("sell", 100, sell_ts)]))
    assert not ok


def test_cooldown_passes_after_window():
    p = CooldownAfterStop(cooldown_minutes=30)
    sell_ts = datetime(2025, 1, 1, 10, 0)
    ok, _ = p.check(_ctx(now=datetime(2025, 1, 1, 12, 0), fills=[_fill("sell", 100, sell_ts)]))
    assert ok


def test_max_consecutive_losses_blocks():
    p = MaxConsecutiveLosses(max_losses=2)
    fills = [
        _fill("buy", 100, "2025-01-01"), _fill("sell", 99, "2025-01-02"),
        _fill("buy", 99, "2025-01-03"), _fill("sell", 98, "2025-01-04"),
    ]
    ok, _ = p.check(_ctx(fills=fills))
    assert not ok


def test_max_consecutive_losses_resets_on_win():
    p = MaxConsecutiveLosses(max_losses=2)
    fills = [
        _fill("buy", 100, "2025-01-01"), _fill("sell", 99, "2025-01-02"),  # loss
        _fill("buy", 99, "2025-01-03"), _fill("sell", 105, "2025-01-04"),  # win → reset
        _fill("buy", 105, "2025-01-05"), _fill("sell", 100, "2025-01-06"),  # 1 loss
    ]
    ok, _ = p.check(_ctx(fills=fills))
    assert ok


def test_drawdown_halt_blocks_below_threshold():
    p = MaxDrawdownHalt(max_dd_pct=10.0)
    ok, _ = p.check(_ctx(equity=8_500, starting=10_000))
    assert not ok


def test_drawdown_halt_passes_above_threshold():
    p = MaxDrawdownHalt(max_dd_pct=10.0)
    ok, _ = p.check(_ctx(equity=9_500, starting=10_000))
    assert ok


def test_chain_short_circuits_on_first_failure():
    chain = ProtectionChain([
        MaxDrawdownHalt(max_dd_pct=10.0),
        CooldownAfterStop(cooldown_minutes=1),  # would also pass, but DD blocks first
    ])
    ok, reason = chain.allow_open(_ctx(equity=8_000, starting=10_000))
    assert not ok
    assert "max_drawdown_halt" in reason
