"""Alpaca broker connector. Uses alpaca-py SDK; falls back to a stub if unavailable."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from ..config.models import AlpacaConfig
from .base import (Account, BaseBroker, Order, OrderSide, OrderStatus,
                   OrderType, Position)

log = logging.getLogger("apex2.broker.alpaca")


_STATUS_MAP = {
    "new": OrderStatus.NEW,
    "accepted": OrderStatus.OPEN,
    "pending_new": OrderStatus.NEW,
    "accepted_for_bidding": OrderStatus.OPEN,
    "stopped": OrderStatus.OPEN,
    "rejected": OrderStatus.REJECTED,
    "suspended": OrderStatus.OPEN,
    "calculated": OrderStatus.OPEN,
    "filled": OrderStatus.FILLED,
    "partially_filled": OrderStatus.PARTIALLY_FILLED,
    "canceled": OrderStatus.CANCELED,
    "expired": OrderStatus.CANCELED,
    "replaced": OrderStatus.OPEN,
    "pending_cancel": OrderStatus.OPEN,
    "pending_replace": OrderStatus.OPEN,
    "done_for_day": OrderStatus.OPEN,
}


class AlpacaBroker(BaseBroker):
    name = "alpaca"

    def __init__(self, cfg: AlpacaConfig):
        self.cfg = cfg
        self._trading = None
        self._data = None

    async def connect(self) -> None:
        try:
            from alpaca.trading.client import TradingClient
            from alpaca.data.historical.stock import StockHistoricalDataClient
        except ImportError:
            log.warning("alpaca-py not installed. pip install alpaca-py")
            return
        if not self.cfg.api_key or not self.cfg.api_secret:
            log.warning("Alpaca credentials missing — connector inert")
            return
        self._trading = TradingClient(
            api_key=self.cfg.api_key,
            secret_key=self.cfg.api_secret,
            paper=self.cfg.paper,
        )
        self._data = StockHistoricalDataClient(
            api_key=self.cfg.api_key,
            secret_key=self.cfg.api_secret,
        )
        log.info("Alpaca connected (paper=%s)", self.cfg.paper)

    async def disconnect(self) -> None:
        self._trading = None
        self._data = None

    async def get_account(self) -> Account:
        if not self._trading:
            return Account(cash=0, equity=0, buying_power=0, portfolio_value=0)
        loop = asyncio.get_event_loop()
        acct = await loop.run_in_executor(None, self._trading.get_account)
        return Account(
            cash=float(acct.cash),
            equity=float(acct.equity),
            buying_power=float(acct.buying_power),
            portfolio_value=float(acct.portfolio_value),
        )

    async def get_positions(self) -> list[Position]:
        if not self._trading:
            return []
        loop = asyncio.get_event_loop()
        positions = await loop.run_in_executor(None, self._trading.get_all_positions)
        return [
            Position(
                symbol=p.symbol,
                qty=float(p.qty),
                avg_entry_price=float(p.avg_entry_price),
                market_value=float(p.market_value),
                unrealized_pl=float(p.unrealized_pl),
            )
            for p in positions
        ]

    async def submit_order(
        self,
        symbol: str,
        side: OrderSide,
        qty: float,
        order_type: OrderType = OrderType.MARKET,
        limit_price: float | None = None,
        stop_price: float | None = None,
        time_in_force: str = "day",
    ) -> Order:
        if not self._trading:
            raise RuntimeError("Alpaca not connected")
        from alpaca.trading.enums import OrderSide as AlpSide, TimeInForce
        from alpaca.trading.requests import (LimitOrderRequest,
                                             MarketOrderRequest,
                                             StopLimitOrderRequest,
                                             StopOrderRequest)

        alp_side = AlpSide.BUY if side == OrderSide.BUY else AlpSide.SELL
        tif = TimeInForce(time_in_force.upper())

        if order_type == OrderType.MARKET:
            req = MarketOrderRequest(symbol=symbol, qty=qty, side=alp_side, time_in_force=tif)
        elif order_type == OrderType.LIMIT:
            req = LimitOrderRequest(
                symbol=symbol, qty=qty, side=alp_side,
                time_in_force=tif, limit_price=limit_price,
            )
        elif order_type == OrderType.STOP:
            req = StopOrderRequest(
                symbol=symbol, qty=qty, side=alp_side,
                time_in_force=tif, stop_price=stop_price,
            )
        else:
            req = StopLimitOrderRequest(
                symbol=symbol, qty=qty, side=alp_side, time_in_force=tif,
                stop_price=stop_price, limit_price=limit_price,
            )
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._trading.submit_order, req)
        return self._to_order(result)

    async def cancel_order(self, order_id: str) -> bool:
        if not self._trading:
            return False
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, self._trading.cancel_order_by_id, order_id)
            return True
        except Exception as e:
            log.warning("cancel_order(%s): %s", order_id, e)
            return False

    async def get_order(self, order_id: str) -> Order:
        if not self._trading:
            raise RuntimeError("Alpaca not connected")
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._trading.get_order_by_id, order_id)
        return self._to_order(result)

    async def is_market_open(self) -> bool:
        if not self._trading:
            return False
        loop = asyncio.get_event_loop()
        clock = await loop.run_in_executor(None, self._trading.get_clock)
        return bool(clock.is_open)

    @staticmethod
    def _to_order(result) -> Order:
        return Order(
            id=str(result.id),
            symbol=result.symbol,
            side=OrderSide.BUY if str(result.side).lower().endswith("buy") else OrderSide.SELL,
            qty=float(result.qty),
            order_type=OrderType(str(result.order_type).lower().replace("ordertype.", "")),
            status=_STATUS_MAP.get(str(result.status).lower().split(".")[-1], OrderStatus.OPEN),
            filled_qty=float(result.filled_qty or 0),
            avg_fill_price=float(result.filled_avg_price) if result.filled_avg_price else None,
            limit_price=float(result.limit_price) if result.limit_price else None,
            stop_price=float(result.stop_price) if result.stop_price else None,
            submitted_at=result.submitted_at if isinstance(result.submitted_at, datetime) else None,
        )
