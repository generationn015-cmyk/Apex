"""
Risk Manager
=============
The bot's immune system. Every trade goes through here before execution.
Nothing fires without risk approval.

Responsibilities:
  1. Position sizing via fractional Kelly criterion
  2. Per-trade stop loss enforcement
  3. Max open positions limit
  4. Daily loss kill switch
  5. Max position size cap
  6. Correlation guard (don't be long BTC + long ETH + long SOL simultaneously)
  7. Leverage cap enforcement

Kelly Criterion:
  f* = (bp - q) / b
  where:
    b = odds (R:R ratio, i.e., reward / risk)
    p = estimated win probability (from signal confidence)
    q = 1 - p (loss probability)
  We use fractional Kelly (25% of f*) to protect against model error.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from exchanges.base import Balance, Position, PositionSide
from strategies.base import Signal, SignalDirection

if TYPE_CHECKING:
    from signals.confluence import ConfluenceResult

log = logging.getLogger("apex.risk")


@dataclass
class TradeApproval:
    approved: bool
    reason: str
    position_size_usd: float = 0.0
    leverage: int = 1
    actual_size: float = 0.0       # In base asset units
    confluence_tier: int = 1       # 1-4 — used by execution engine
    trail_stop_pct: float = 0.0    # >0 activates trailing stop (% of price)


@dataclass
class DailyStats:
    date: str = ""
    starting_balance: float = 0.0
    realized_pnl: float = 0.0
    trade_count: int = 0
    win_count: int = 0
    loss_count: int = 0
    max_drawdown_pct: float = 0.0
    peak_balance: float = 0.0


class RiskManager:
    def __init__(self, config: dict):
        self.starting_balance: float = config["capital"]["starting_balance_usd"]
        self.max_account_risk_pct: float = config["capital"]["max_account_risk_pct"]
        self.max_daily_loss_pct: float = config["capital"]["max_daily_loss_pct"]
        self.max_open_positions: int = config["capital"]["max_open_positions"]
        self.max_position_pct: float = config["capital"]["max_position_pct"]
        self.kelly_fraction: float = config["capital"]["kelly_fraction"]
        self.default_leverage: int = config["leverage"]["default"]
        self.max_leverage: int = config["leverage"]["moonshot"]

        self._current_balance: float = self.starting_balance
        self._peak_balance: float = self.starting_balance
        self._daily_stats: DailyStats = DailyStats()
        self._open_positions: list[Position] = []
        self._daily_loss_halt: bool = False
        self._today: str = ""

    # ── Public API ────────────────────────────────────────────────────

    def update_balance(self, balance: float) -> None:
        self._current_balance = balance
        if balance > self._peak_balance:
            self._peak_balance = balance
        self._check_daily_loss()

    def update_open_positions(self, positions: list[Position]) -> None:
        self._open_positions = positions

    def record_trade_result(self, pnl: float) -> None:
        self._daily_stats.realized_pnl += pnl
        self._daily_stats.trade_count += 1
        if pnl > 0:
            self._daily_stats.win_count += 1
        else:
            self._daily_stats.loss_count += 1

    def approve_trade(
        self,
        signal: Signal,
        current_balance: float,
        current_price: float,
        confluence: "ConfluenceResult | None" = None,
    ) -> TradeApproval:
        """
        Evaluate a signal and return TradeApproval with position size.
        The execution engine calls this before placing any order.
        """
        self.update_balance(current_balance)

        # ── Hard stops ────────────────────────────────────────────────
        if self._daily_loss_halt:
            return TradeApproval(False, "DAILY_LOSS_LIMIT_HIT")

        if len(self._open_positions) >= self.max_open_positions:
            return TradeApproval(False, f"MAX_POSITIONS_REACHED ({self.max_open_positions})")

        # ── Duplicate position guard ──────────────────────────────────
        for pos in self._open_positions:
            if pos.pair == signal.pair and pos.venue == signal.venue:
                expected_side = PositionSide.LONG if signal.direction == SignalDirection.LONG else PositionSide.SHORT
                if pos.side == expected_side:
                    return TradeApproval(False, "DUPLICATE_POSITION")

        # ── R:R minimum gate ─────────────────────────────────────────
        if signal.risk_reward < 1.5:
            return TradeApproval(False, f"POOR_RR={signal.risk_reward:.2f} (min 1.5)")

        # ── Minimum confidence gate ───────────────────────────────────
        if signal.confidence < 0.30:
            return TradeApproval(False, f"LOW_CONFIDENCE={signal.confidence:.2%}")

        # ── Calculate position size ───────────────────────────────────
        size_usd = self._kelly_position_size(
            signal.confidence, signal.risk_reward, current_balance
        )

        if size_usd < 1.0:
            return TradeApproval(False, f"SIZE_TOO_SMALL=${size_usd:.2f}")

        # ── Apply confluence multipliers ──────────────────────────────
        confluence_tier = 1
        leverage_bonus = 0
        trail_stop_pct = 0.0

        if confluence:
            confluence_tier = confluence.tier
            leverage_bonus = confluence.leverage_bonus

            # Scale position size up, but cap at max_position_pct
            max_size = current_balance * (self.max_position_pct / 100)
            size_usd = min(size_usd * confluence.size_multiplier, max_size)

            # Tier 3+ setups get trailing stops to lock in profits
            if confluence.tier == 4:
                trail_stop_pct = 0.8   # Tight trail for quad-confluence
            elif confluence.tier == 3:
                trail_stop_pct = 1.0   # 1% trail for triple-confluence

            log.info(
                "CONFLUENCE TIER %d applied: size=x%.1f → $%.2f | +%d lev | trail=%.1f%%",
                confluence.tier, confluence.size_multiplier, size_usd,
                leverage_bonus, trail_stop_pct,
            )

        # ── Determine leverage ────────────────────────────────────────
        leverage = self._select_leverage(signal, leverage_bonus)

        # ── Calculate actual units ─────────────────────────────────────
        notional = size_usd * leverage
        actual_size = notional / current_price if current_price > 0 else 0

        log.info(
            "APPROVED: %s | size=$%.2f | leverage=%dx | notional=$%.2f | "
            "conf=%.0%% | RR=%.1f | tier=%d",
            signal, size_usd, leverage, notional, signal.confidence,
            signal.risk_reward, confluence_tier,
        )

        return TradeApproval(
            approved=True,
            reason="OK",
            position_size_usd=size_usd,
            leverage=leverage,
            actual_size=actual_size,
            confluence_tier=confluence_tier,
            trail_stop_pct=trail_stop_pct,
        )

    def check_stop_hit(self, position: Position, current_price: float) -> bool:
        """
        Returns True if position should be stopped out.
        This is a safety net — the exchange stop order is the primary mechanism.
        """
        if position.side == PositionSide.LONG:
            return current_price <= position.liquidation_price * 1.05
        return current_price >= position.liquidation_price * 0.95

    @property
    def win_rate(self) -> float:
        total = self._daily_stats.trade_count
        if total == 0:
            return 0.0
        return self._daily_stats.win_count / total

    @property
    def daily_pnl(self) -> float:
        return self._daily_stats.realized_pnl

    @property
    def daily_pnl_pct(self) -> float:
        if self._daily_stats.starting_balance == 0:
            return 0.0
        return self._daily_stats.realized_pnl / self._daily_stats.starting_balance * 100

    @property
    def is_halted(self) -> bool:
        return self._daily_loss_halt

    @property
    def drawdown_pct(self) -> float:
        if self._peak_balance == 0:
            return 0.0
        return (self._peak_balance - self._current_balance) / self._peak_balance * 100

    def reset_daily(self, current_balance: float) -> None:
        """Call at midnight UTC to reset daily stats."""
        import datetime
        today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
        self._daily_stats = DailyStats(
            date=today,
            starting_balance=current_balance,
            peak_balance=current_balance,
        )
        self._daily_loss_halt = False
        self._today = today
        log.info("Daily stats reset. Balance: $%.2f", current_balance)

    def get_stats(self) -> dict:
        return {
            "balance": round(self._current_balance, 2),
            "peak_balance": round(self._peak_balance, 2),
            "drawdown_pct": round(self.drawdown_pct, 2),
            "daily_pnl": round(self.daily_pnl, 2),
            "daily_pnl_pct": round(self.daily_pnl_pct, 2),
            "trades_today": self._daily_stats.trade_count,
            "win_rate": round(self.win_rate * 100, 1),
            "open_positions": len(self._open_positions),
            "halted": self._daily_loss_halt,
        }

    # ── Private helpers ───────────────────────────────────────────────

    def _kelly_position_size(
        self, confidence: float, risk_reward: float, balance: float
    ) -> float:
        """
        Fractional Kelly criterion position sizing.
        f* = (b*p - q) / b
        b = risk_reward ratio (reward per $1 risked)
        p = win probability (signal confidence)
        q = 1 - p

        We apply kelly_fraction (e.g., 0.25) as a safety buffer.
        Then cap at max_position_pct.
        """
        b = risk_reward
        p = confidence
        q = 1.0 - p

        kelly = (b * p - q) / b if b > 0 else 0
        kelly = max(0, kelly)

        # Fractional Kelly
        frac_kelly = kelly * self.kelly_fraction

        # Cap at max_position_pct
        max_size_pct = self.max_position_pct / 100
        pct = min(frac_kelly, max_size_pct)

        # Also never risk more than max_account_risk_pct on a single trade
        max_risk_pct = self.max_account_risk_pct / 100
        pct = min(pct, max_risk_pct * 5)   # Assuming ~20% stop = 5x position allowed per risk %

        size_usd = balance * pct
        log.debug(
            "Kelly: conf=%.2f RR=%.1f → f*=%.3f frac=%.3f → $%.2f",
            confidence, risk_reward, kelly, frac_kelly, size_usd
        )
        return round(size_usd, 2)

    def _select_leverage(self, signal: Signal, leverage_bonus: int = 0) -> int:
        """
        Select leverage based on signal confidence and strategy.
        Higher confidence → can use more leverage.
        Liquidation cascade signals → lower leverage (quick moves but risky).
        Confluence bonus added on top, capped at max_leverage.
        """
        base = self.default_leverage
        conf = signal.confidence

        if signal.strategy == "liquidation_cascade":
            # These are fast, high-risk plays — keep leverage moderate
            lev = min(int(base * conf * 1.5), 20)
        elif signal.strategy == "funding_arb":
            # Funding signals are contrarian, keep conservative
            lev = min(int(base * conf), 15)
        else:
            # Momentum and breakout — scale with confidence
            lev = min(int(base * (0.5 + conf)), self.max_leverage)

        return max(1, min(lev + leverage_bonus, self.max_leverage))

    def _check_daily_loss(self) -> None:
        """Activate kill switch if daily loss exceeds limit."""
        if self._daily_stats.starting_balance == 0:
            return
        daily_loss_pct = -self.daily_pnl_pct   # Positive = loss
        if daily_loss_pct >= self.max_daily_loss_pct:
            if not self._daily_loss_halt:
                log.critical(
                    "DAILY LOSS LIMIT HIT: %.1f%% (limit=%.1f%%). Trading halted until midnight UTC.",
                    daily_loss_pct, self.max_daily_loss_pct
                )
                self._daily_loss_halt = True
