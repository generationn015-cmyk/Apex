"""Execution router. Routes BTOrder-style decisions to a live broker (paper or real).

In paper mode this still hits Alpaca's paper endpoint (it simulates the full
order lifecycle for free). In live mode it hits Alpaca's live endpoint.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from tenacity import retry, stop_after_attempt, wait_exponential

from ..agents.advisor import pre_trade_veto, trade_journal
from ..brokers.base import BaseBroker, OrderSide, OrderStatus, OrderType

log = logging.getLogger("apex2.execution")


@dataclass
class ExecRequest:
    symbol: str
    side: str          # "buy" | "sell"
    qty: float
    order_type: str = "market"
    limit_price: float | None = None
    stop_price: float | None = None
    reason: str = ""


class ExecutionRouter:
    def __init__(self, broker: BaseBroker, dry_run: bool = False, use_advisor: bool = False):
        self.broker = broker
        self.dry_run = dry_run
        self.use_advisor = use_advisor

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    async def submit(self, req: ExecRequest, strategy: str = ""):
        side = OrderSide.BUY if req.side == "buy" else OrderSide.SELL
        otype = OrderType(req.order_type)
        if self.dry_run:
            log.info("DRY-RUN %s %s %s qty=%s reason=%s",
                     req.order_type.upper(), side.value, req.symbol, req.qty, req.reason)
            return None
        if req.qty <= 0:
            log.debug("skip zero/negative qty for %s", req.symbol)
            return None

        # Optional Claude pre-trade veto. Defaults allow=True; only blocks for
        # obvious obstacles (earnings, halt, etc).
        if self.use_advisor and req.side == "buy":
            veto = pre_trade_veto(req.symbol, req.side, strategy, req.reason)
            if not veto.allow:
                log.warning("advisor vetoed %s %s: %s", req.side, req.symbol, veto.reason)
                trade_journal({
                    "event": "veto",
                    "symbol": req.symbol, "side": req.side, "qty": req.qty,
                    "strategy": strategy, "reason": req.reason, "veto_reason": veto.reason,
                })
                return None

        order = await self.broker.submit_order(
            symbol=req.symbol,
            side=side,
            qty=req.qty,
            order_type=otype,
            limit_price=req.limit_price,
            stop_price=req.stop_price,
        )
        log.info("submitted %s %s %s qty=%s id=%s status=%s reason=%s",
                 req.order_type.upper(), side.value, req.symbol, req.qty, order.id, order.status.value, req.reason)
        trade_journal({
            "event": "submit",
            "symbol": req.symbol, "side": req.side, "qty": req.qty,
            "strategy": strategy, "reason": req.reason, "order_id": order.id,
        })
        return order

    async def wait_for_fill(self, order_id: str, timeout_s: float = 30.0):
        deadline = asyncio.get_event_loop().time() + timeout_s
        while asyncio.get_event_loop().time() < deadline:
            o = await self.broker.get_order(order_id)
            if o.status in (OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED):
                return o
            await asyncio.sleep(1)
        return await self.broker.get_order(order_id)
