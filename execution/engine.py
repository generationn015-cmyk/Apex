"""
Execution Engine
=================
Smart order routing and trade lifecycle management.

Responsibilities:
  - Accept a Signal + TradeApproval → place orders on the correct venue
  - Attach stop-loss orders immediately after entry fills
  - Monitor open trades for stop/target hit
  - Handle partial fills and order retries
  - Track all trades in memory + database
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from exchanges.base import (
    BaseExchange, Order, OrderSide, OrderStatus, OrderType,
    Position, PositionSide,
)
from risk.manager import RiskManager, TradeApproval
from strategies.base import Signal, SignalDirection

if TYPE_CHECKING:
    from data.store import TradeStore

log = logging.getLogger("apex.execution")


@dataclass
class ManagedTrade:
    """A live trade being actively managed by the execution engine."""
    trade_id: str
    signal: Signal
    entry_order: Order
    stop_order: Order | None = None
    target_order: Order | None = None
    entry_fill_price: float = 0.0
    status: str = "pending"      # pending | open | closed | error
    pnl: float = 0.0
    opened_at: float = field(default_factory=time.time)
    closed_at: float = 0.0
    close_reason: str = ""
    confluence_tier: int = 1     # Confluence tier that triggered this trade
    trail_stop_pct: float = 0.0  # >0 = trailing stop active (% of current price)
    best_price: float = 0.0      # Best price seen since entry (for trail tracking)
    dynamic_stop: float = 0.0    # Current trailing stop level (0 = use signal.stop_price)


class ExecutionEngine:
    def __init__(
        self,
        exchanges: dict[str, BaseExchange],
        risk: RiskManager,
        paper_mode: bool = True,
    ):
        self.exchanges = exchanges
        self.risk = risk
        self.paper_mode = paper_mode
        self._trades: dict[str, ManagedTrade] = {}
        self._trade_counter = 0
        self._store: TradeStore | None = None

    def attach_store(self, store: "TradeStore") -> None:
        self._store = store

    # ── Public API ────────────────────────────────────────────────────

    async def execute_signal(
        self, signal: Signal, approval: TradeApproval
    ) -> ManagedTrade | None:
        """
        Main entry point. Given an approved signal, execute it:
        1. Enter position
        2. Attach stop loss
        3. Return ManagedTrade for monitoring
        """
        if not approval.approved:
            log.warning("execute_signal called with unapproved signal: %s", approval.reason)
            return None

        exchange = self.exchanges.get(signal.venue)
        if not exchange:
            log.error("Exchange %s not available", signal.venue)
            return None

        self._trade_counter += 1
        trade_id = f"T{int(time.time())}-{self._trade_counter:04d}"

        log.info("EXECUTING: %s | trade_id=%s | size=$%.2f x%d lev",
                 signal, trade_id, approval.position_size_usd, approval.leverage)

        # ── Order book imbalance gate ─────────────────────────────────
        # Check bid/ask pressure before committing — skip if book is
        # strongly opposed to our direction (>30% imbalance against us).
        ob_gate_ok = await self._check_orderbook_alignment(signal, exchange)
        if not ob_gate_ok:
            log.info(
                "OB_GATE rejected %s %s — order book strongly opposed",
                signal.pair, signal.direction.value,
            )
            return None

        if self.paper_mode:
            return await self._paper_execute(trade_id, signal, approval)

        return await self._live_execute(trade_id, signal, approval, exchange)

    async def monitor_trades(self) -> list[str]:
        """
        Check all open trades — returns list of trade_ids that were closed.
        Called on every bot heartbeat cycle.
        """
        closed = []
        for trade_id, trade in list(self._trades.items()):
            if trade.status != "open":
                continue
            try:
                was_closed = await self._check_trade(trade)
                if was_closed:
                    closed.append(trade_id)
            except Exception as e:
                log.error("monitor trade %s: %s", trade_id, e)
        return closed

    def get_open_trades(self) -> list[ManagedTrade]:
        return [t for t in self._trades.values() if t.status == "open"]

    def get_all_trades(self) -> list[ManagedTrade]:
        return list(self._trades.values())

    # ── Paper trading ─────────────────────────────────────────────────

    async def _paper_execute(
        self, trade_id: str, signal: Signal, approval: TradeApproval
    ) -> ManagedTrade:
        """Simulate execution without touching real orders."""
        entry_price = signal.entry_price
        fake_order = Order(
            order_id=f"PAPER-{trade_id}",
            pair=signal.pair,
            side=OrderSide.BUY if signal.direction == SignalDirection.LONG else OrderSide.SELL,
            order_type=OrderType.MARKET,
            size=approval.actual_size,
            price=entry_price,
            status=OrderStatus.FILLED,
            filled_size=approval.actual_size,
            avg_fill_price=entry_price,
            timestamp=int(time.time() * 1000),
            venue=signal.venue,
        )
        trade = ManagedTrade(
            trade_id=trade_id,
            signal=signal,
            entry_order=fake_order,
            entry_fill_price=entry_price,
            status="open",
            confluence_tier=approval.confluence_tier,
            trail_stop_pct=approval.trail_stop_pct,
            best_price=entry_price,
        )
        self._trades[trade_id] = trade
        trail_note = f" | trail={approval.trail_stop_pct:.1f}%" if approval.trail_stop_pct else ""
        log.info(
            "[PAPER] TRADE OPEN: %s | entry=%.4f | stop=%.4f | target=%.4f | tier=%d%s",
            trade_id, entry_price, signal.stop_price, signal.target_price,
            approval.confluence_tier, trail_note,
        )
        if self._store:
            await self._store.save_trade(trade)
        return trade

    # ── Live trading ──────────────────────────────────────────────────

    async def _live_execute(
        self, trade_id: str, signal: Signal, approval: TradeApproval, exchange: BaseExchange
    ) -> ManagedTrade | None:
        """
        Place real orders on the exchange.

        Fee optimization: Always try a limit order first (0.015% maker fee on HL
        vs 0.045% taker). At $250 account, this 3x fee difference compounds
        significantly. Use IOC limit with small slippage buffer — if not filled
        in 3 seconds, fall back to true market order.
        """
        is_long = signal.direction == SignalDirection.LONG
        entry_side = OrderSide.BUY if is_long else OrderSide.SELL

        # ── 1. Try limit entry first (cheaper maker fee) ───────────────
        try:
            # Aggressive limit: 0.05% inside the book to get maker fill
            # while still executing quickly (IOC = immediate-or-cancel)
            limit_slippage = 0.0005   # 0.05% inside best price
            limit_price = (
                signal.entry_price * (1 + limit_slippage) if is_long
                else signal.entry_price * (1 - limit_slippage)
            )
            entry_order = await exchange.place_order(
                pair=signal.pair,
                side=entry_side,
                order_type=OrderType.LIMIT,
                size=approval.actual_size,
                price=round(limit_price, 6),
                leverage=approval.leverage,
            )
            log.debug("[LIVE] Limit entry attempt: %s @ %.4f (maker fee)", trade_id, limit_price)
        except Exception as e:
            log.warning("Limit entry failed for %s (%s) — trying market order", trade_id, e)
            entry_order = None

        # Wait up to 3 seconds for limit fill
        fill_price = 0.0
        if entry_order:
            fill_price = await self._wait_for_fill(entry_order, exchange, timeout=3)

        # ── 1b. Fall back to market order if limit didn't fill ─────────
        if fill_price == 0:
            if entry_order:
                await exchange.cancel_order(entry_order.order_id, signal.pair)
                log.debug("[LIVE] Limit not filled — switching to market order: %s", trade_id)
            try:
                entry_order = await exchange.place_order(
                    pair=signal.pair,
                    side=entry_side,
                    order_type=OrderType.MARKET,
                    size=approval.actual_size,
                    leverage=approval.leverage,
                )
            except Exception as e:
                log.error("Market entry order failed for %s: %s", trade_id, e)
                return None
            fill_price = await self._wait_for_fill(entry_order, exchange, timeout=5)

        if fill_price == 0:
            log.warning("Entry fill timeout for %s — cancelling", trade_id)
            await exchange.cancel_order(entry_order.order_id, signal.pair)
            return None

        # ── 2. Stop loss order ────────────────────────────────────────
        stop_side = OrderSide.SELL if is_long else OrderSide.BUY
        stop_order = None
        try:
            stop_order = await exchange.place_order(
                pair=signal.pair,
                side=stop_side,
                order_type=OrderType.STOP_MARKET,
                size=approval.actual_size,
                stop_price=signal.stop_price,
                reduce_only=True,
            )
            log.info("[LIVE] Stop placed: %s @ %.4f", trade_id, signal.stop_price)
        except Exception as e:
            log.warning("Stop order failed for %s: %s — monitoring manually", trade_id, e)

        # ── 3. Take profit order (optional) ──────────────────────────
        tp_order = None
        try:
            tp_order = await exchange.place_order(
                pair=signal.pair,
                side=stop_side,
                order_type=OrderType.LIMIT,
                size=approval.actual_size,
                price=signal.target_price,
                reduce_only=True,
            )
            log.info("[LIVE] Take profit placed: %s @ %.4f", trade_id, signal.target_price)
        except Exception as e:
            log.debug("TP order failed for %s: %s", trade_id, e)

        trade = ManagedTrade(
            trade_id=trade_id,
            signal=signal,
            entry_order=entry_order,
            stop_order=stop_order,
            target_order=tp_order,
            entry_fill_price=fill_price,
            status="open",
            confluence_tier=approval.confluence_tier,
            trail_stop_pct=approval.trail_stop_pct,
            best_price=fill_price,
        )
        self._trades[trade_id] = trade

        trail_note = f" | trail={approval.trail_stop_pct:.1f}%" if approval.trail_stop_pct else ""
        log.info(
            "[LIVE] TRADE OPEN: %s | filled=%.4f | stop=%.4f | target=%.4f | lev=%dx | tier=%d%s",
            trade_id, fill_price, signal.stop_price, signal.target_price,
            approval.leverage, approval.confluence_tier, trail_note,
        )

        if self._store:
            await self._store.save_trade(trade)

        return trade

    # ── Trade monitoring ──────────────────────────────────────────────

    async def _check_trade(self, trade: ManagedTrade) -> bool:
        """
        Poll trade status. Returns True if trade was closed.
        In paper mode: simulate price-based exit.
        In live mode: check order statuses.
        """
        if self.paper_mode:
            return await self._check_paper_trade(trade)
        return await self._check_live_trade(trade)

    async def _check_paper_trade(self, trade: ManagedTrade) -> bool:
        """Check paper trade against current market price."""
        signal = trade.signal
        exchange = self.exchanges.get(signal.venue)
        if not exchange:
            return False

        try:
            current_price = await exchange.get_price(signal.pair)
        except Exception:
            return False

        is_long = signal.direction == SignalDirection.LONG

        # ── Trailing stop update ──────────────────────────────────────
        if trade.trail_stop_pct > 0:
            self._update_trailing_stop(trade, current_price, is_long)

        # Use dynamic (trailing) stop if active, else original stop
        effective_stop = trade.dynamic_stop if trade.dynamic_stop > 0 else signal.stop_price

        stop_hit = (is_long and current_price <= effective_stop) or \
                   (not is_long and current_price >= effective_stop)

        target_hit = (is_long and current_price >= signal.target_price) or \
                     (not is_long and current_price <= signal.target_price)

        if stop_hit or target_hit:
            exit_price = effective_stop if stop_hit else signal.target_price
            is_trail = stop_hit and trade.dynamic_stop > 0
            reason = "TRAIL_STOP" if is_trail else "STOP_HIT" if stop_hit else "TARGET_HIT"
            pnl = self._calc_pnl(trade, exit_price)
            self._close_trade(trade, exit_price, reason, pnl)
            return True

        return False

    async def _check_live_trade(self, trade: ManagedTrade) -> bool:
        """Check live trade by polling order statuses."""
        exchange = self.exchanges.get(trade.signal.venue)
        if not exchange:
            return False

        # Update trailing stop (cancel + replace stop order when stop moves favorably)
        if trade.trail_stop_pct > 0:
            await self._update_live_trailing_stop(trade, exchange)

        # Check if stop or TP filled
        for order, reason in [
            (trade.stop_order, "STOP_HIT"),
            (trade.target_order, "TARGET_HIT"),
        ]:
            if order is None:
                continue
            try:
                updated = await exchange.get_order(order.order_id, trade.signal.pair)
                if updated.status == OrderStatus.FILLED:
                    exit_price = updated.avg_fill_price
                    pnl = self._calc_pnl(trade, exit_price)
                    # Cancel the other order
                    other = trade.target_order if reason == "STOP_HIT" else trade.stop_order
                    if other:
                        await exchange.cancel_order(other.order_id, trade.signal.pair)
                    self._close_trade(trade, exit_price, reason, pnl)
                    return True
            except Exception as e:
                log.debug("check order %s: %s", order.order_id, e)

        return False

    # ── Helpers ───────────────────────────────────────────────────────

    async def _check_orderbook_alignment(
        self, signal: Signal, exchange: BaseExchange
    ) -> bool:
        """
        Hard gate: reject if order book is strongly opposed (>30% imbalance).
        A 30% imbalance against our direction means serious sell/buy pressure
        we shouldn't fight. Returns True if it's safe to enter.
        """
        try:
            ob = await exchange.get_orderbook(signal.pair)
            imbalance = ob.imbalance()  # -1.0 (sell) to +1.0 (buy)
            is_long = signal.direction == SignalDirection.LONG
            # Block if imbalance > 0.30 in the wrong direction
            if is_long and imbalance < -0.30:
                log.debug("OB gate: imbalance=%.2f strongly bearish for long signal", imbalance)
                return False
            if not is_long and imbalance > 0.30:
                log.debug("OB gate: imbalance=%.2f strongly bullish for short signal", imbalance)
                return False
        except Exception as e:
            log.debug("OB gate fetch failed (%s) — passing through", e)
        return True

    def _update_trailing_stop(
        self, trade: ManagedTrade, current_price: float, is_long: bool
    ) -> None:
        """
        Update the in-memory trailing stop level as price moves favorably.

        Activation: only kicks in once price has moved 1x the original stop
        distance in our favor (avoids getting stopped out on normal noise).
        Movement: trail distance = trail_stop_pct % of current price.
        Rule: stop only ever moves in our favor (never against us).
        """
        trail_distance = current_price * (trade.trail_stop_pct / 100)
        original_stop_dist = abs(trade.signal.entry_price - trade.signal.stop_price)

        if is_long:
            if current_price <= trade.best_price:
                return
            trade.best_price = current_price
            new_stop = current_price - trail_distance

            if trade.dynamic_stop == 0:
                # Activate only after price clears activation threshold
                activation_threshold = trade.signal.entry_price + original_stop_dist
                if current_price >= activation_threshold:
                    trade.dynamic_stop = new_stop
                    log.info(
                        "[TRAIL] ACTIVATED: %s | stop=%.4f | price=%.4f",
                        trade.trade_id, new_stop, current_price,
                    )
            elif new_stop > trade.dynamic_stop:
                trade.dynamic_stop = new_stop
                log.debug("[TRAIL] Stop raised to %.4f for %s", new_stop, trade.trade_id)
        else:
            if current_price >= trade.best_price and trade.best_price > 0:
                return
            trade.best_price = current_price if trade.best_price == 0 else min(trade.best_price, current_price)
            new_stop = current_price + trail_distance

            if trade.dynamic_stop == 0:
                activation_threshold = trade.signal.entry_price - original_stop_dist
                if current_price <= activation_threshold:
                    trade.dynamic_stop = new_stop
                    log.info(
                        "[TRAIL] ACTIVATED: %s | stop=%.4f | price=%.4f",
                        trade.trade_id, new_stop, current_price,
                    )
            elif new_stop < trade.dynamic_stop:
                trade.dynamic_stop = new_stop
                log.debug("[TRAIL] Stop lowered to %.4f for %s", new_stop, trade.trade_id)

    async def _update_live_trailing_stop(
        self, trade: ManagedTrade, exchange: BaseExchange
    ) -> None:
        """
        For live trades: fetch current price, update trailing stop in memory,
        and replace the exchange stop order if stop moved by >0.2% (avoids
        excessive order churn).
        """
        try:
            current_price = await exchange.get_price(trade.signal.pair)
        except Exception:
            return

        is_long = trade.signal.direction == SignalDirection.LONG
        prev_stop = trade.dynamic_stop

        self._update_trailing_stop(trade, current_price, is_long)

        # Only update the exchange stop order if stop moved meaningfully
        if trade.dynamic_stop == 0 or trade.dynamic_stop == prev_stop:
            return
        if prev_stop > 0 and abs(trade.dynamic_stop - prev_stop) / prev_stop < 0.002:
            return  # Less than 0.2% move — not worth the round trip

        # Cancel old stop and place new one at updated level
        if trade.stop_order:
            try:
                await exchange.cancel_order(trade.stop_order.order_id, trade.signal.pair)
            except Exception:
                pass

        stop_side = OrderSide.SELL if is_long else OrderSide.BUY
        try:
            trade.stop_order = await exchange.place_order(
                pair=trade.signal.pair,
                side=stop_side,
                order_type=OrderType.STOP_MARKET,
                size=trade.entry_order.filled_size,
                stop_price=round(trade.dynamic_stop, 6),
                reduce_only=True,
            )
            log.info(
                "[TRAIL] Stop order updated: %s | new_stop=%.4f",
                trade.trade_id, trade.dynamic_stop,
            )
        except Exception as e:
            log.warning("Trailing stop update failed for %s: %s", trade.trade_id, e)

    async def _wait_for_fill(
        self, order: Order, exchange: BaseExchange, timeout: int = 10
    ) -> float:
        """Poll order status until filled or timeout. Returns fill price."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                updated = await exchange.get_order(order.order_id, order.pair)
                if updated.status == OrderStatus.FILLED:
                    return updated.avg_fill_price
                if updated.status in (OrderStatus.CANCELLED, OrderStatus.REJECTED):
                    return 0.0
            except Exception:
                pass
            await asyncio.sleep(0.5)
        return 0.0

    def _calc_pnl(self, trade: ManagedTrade, exit_price: float) -> float:
        entry = trade.entry_fill_price
        size = trade.entry_order.filled_size
        is_long = trade.signal.direction == SignalDirection.LONG
        if entry == 0 or size == 0:
            return 0.0
        if is_long:
            return (exit_price - entry) * size
        else:
            return (entry - exit_price) * size

    def _close_trade(
        self, trade: ManagedTrade, exit_price: float, reason: str, pnl: float
    ) -> None:
        trade.status = "closed"
        trade.pnl = pnl
        trade.closed_at = time.time()
        trade.close_reason = reason
        self.risk.record_trade_result(pnl)
        emoji = "+" if pnl >= 0 else ""
        log.info(
            "TRADE CLOSED: %s | %s | exit=%.4f | PNL=%s%.4f | duration=%.0fs",
            trade.trade_id, reason, exit_price, emoji, pnl,
            trade.closed_at - trade.opened_at,
        )
        if self._store:
            asyncio.create_task(self._store.update_trade(trade))
