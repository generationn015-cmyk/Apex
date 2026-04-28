"""Risk manager tests."""
from __future__ import annotations

from apex2.config.models import CapitalConfig
from apex2.risk.manager import GateInput, RiskManager, SizingInput


def _cfg(**over) -> CapitalConfig:
    base = dict(
        starting_balance_usd=10_000,
        risk_per_trade_pct=1.0,
        max_daily_loss_pct=3.0,
        max_open_positions=5,
        max_position_pct=20.0,
        kelly_fraction=0.25,
    )
    base.update(over)
    return CapitalConfig(**base)


def test_fixed_fraction_size_respects_stop_distance():
    rm = RiskManager(_cfg(risk_per_trade_pct=1.0))
    qty = rm.size(SizingInput(equity=10_000, entry_price=100, stop_price=95))
    # 1% of 10k = $100 risk; $5/share stop → 20 shares.
    assert abs(qty - 20.0) < 1e-6


def test_size_capped_by_max_position_pct():
    rm = RiskManager(_cfg(risk_per_trade_pct=5.0, max_position_pct=5.0))
    qty = rm.size(SizingInput(equity=10_000, entry_price=100, stop_price=99))
    # Without cap: 5% risk / $1 stop = 500 shares. Cap is 5% of 10k = $500 / $100 = 5 shares.
    assert qty == 5


def test_kelly_zero_when_no_edge():
    rm = RiskManager(_cfg())
    qty = rm.size(SizingInput(
        equity=10_000, entry_price=100, stop_price=95,
        win_rate=0.5, avg_win_r=1.0, method="kelly",
    ))
    assert qty == 0.0


def test_gate_blocks_on_daily_loss_kill():
    rm = RiskManager(_cfg(max_daily_loss_pct=3.0))
    ok, reason = rm.can_open(GateInput(
        equity=9_700, starting_equity=10_000,
        open_symbols=set(), target_symbol="X",
        notional=1000, daily_pnl=-300,
    ))
    assert not ok
    assert "daily" in reason.lower()


def test_gate_blocks_on_max_positions():
    rm = RiskManager(_cfg(max_open_positions=3))
    ok, _ = rm.can_open(GateInput(
        equity=10_000, starting_equity=10_000,
        open_symbols={"A", "B", "C"}, target_symbol="D",
        notional=500, daily_pnl=0,
    ))
    assert not ok


def test_gate_passes_normal():
    rm = RiskManager(_cfg())
    ok, _ = rm.can_open(GateInput(
        equity=10_000, starting_equity=10_000,
        open_symbols=set(), target_symbol="A",
        notional=1500, daily_pnl=0,
    ))
    assert ok
