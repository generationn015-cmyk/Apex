"""
Alpaca paper-trading exchange connector.

Uses alpaca-py for account, order, position, and stock market-data access.
Paper mode is enforced by default; set paper=false only after explicit approval.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from .base import (
    Balance, BaseExchange, Candle, FundingRate, Order, OrderBook,
    OrderSide, OrderStatus, OrderType, Position, PositionSide,
)

log = logging.getLogger("apex.alpaca")

_TIMEFRAMES = {
    "1m": ("Minute", 1),
    "5m": ("Minute", 5),
    "15m": ("Minute", 15),
    "1h": ("Hour", 1),
    "1d": ("Day", 1),
}


class AlpacaExchange(BaseExchange):
    """Alpaca equities/crypto connector, intended for paper trading first."""

    name = "alpaca"

    def __init__(self, config: dict):
        super().__init__(config)
        self.api_key = config.get("api_key", "")
        self.api_secret = config.get("api_secret", "")
        self.paper = bool(config.get("paper", True))
        self.feed = config.get("feed", "iex")
        self._trading_client: Any | None = None
        self._stock_data_client: Any | None = None

    async def connect(self) -> None:
        if not self.paper:
            raise RuntimeError("Alpaca live mode is disabled for now; keep paper=true.")
        if not self.api_key or not self.api_secret:
            raise RuntimeError("Alpaca API credentials missing. Set APCA_API_KEY_ID and APCA_API_SECRET_KEY.")

        def _connect():
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.trading.client import TradingClient

            trading = TradingClient(self.api_key, self.api_secret, paper=True)
            data = StockHistoricalDataClient(self.api_key, self.api_secret)
            account = trading.get_account()
            return trading, data, account

        self._trading_client, self._stock_data_client, account = await asyncio.to_thread(_connect)
        log.info(
            "Alpaca paper connected — portfolio=%s buying_power=%s",
            getattr(account, "portfolio_value", "unknown"),
            getattr(account, "buying_power", "unknown"),
        )

    async def disconnect(self) -> None:
        self._trading_client = None
        self._stock_data_client = None
        log.info("Alpaca disconnected")

    def _require_clients(self) -> tuple[Any, Any]:
        if self._trading_client is None or self._stock_data_client is None:
            raise RuntimeError("Alpaca is not connected")
        return self._trading_client, self._stock_data_client

    async def get_candles(self, pair: str, timeframe: str, limit: int = 200) -> list[Candle]:
        _, data = self._require_clients()

        def _fetch():
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

            tf = _to_alpaca_timeframe(timeframe, TimeFrame, TimeFrameUnit)
            start = datetime.now(timezone.utc) - timedelta(days=max(5, limit))
            request = StockBarsRequest(
                symbol_or_symbols=pair,
                timeframe=tf,
                start=start,
                limit=limit,
                feed=self.feed,
            )
            return data.get_stock_bars(request)

        barset = await asyncio.to_thread(_fetch)
        bars = _extract_symbol_records(barset, pair)
        return [
            Candle(
                timestamp=_timestamp_ms(getattr(bar, "timestamp", None)),
                open=float(getattr(bar, "open", 0.0)),
                high=float(getattr(bar, "high", 0.0)),
                low=float(getattr(bar, "low", 0.0)),
                close=float(getattr(bar, "close", 0.0)),
                volume=float(getattr(bar, "volume", 0.0)),
                pair=pair,
                timeframe=timeframe,
            )
            for bar in bars[-limit:]
        ]

    async def get_orderbook(self, pair: str, depth: int = 20) -> OrderBook:
        quote = await self._latest_quote(pair)
        bid = float(getattr(quote, "bid_price", 0.0) or 0.0)
        ask = float(getattr(quote, "ask_price", 0.0) or 0.0)
        bid_size = float(getattr(quote, "bid_size", 0.0) or 0.0)
        ask_size = float(getattr(quote, "ask_size", 0.0) or 0.0)
        return OrderBook(
            timestamp=_timestamp_ms(getattr(quote, "timestamp", None)),
            bids=[(bid, bid_size)] if bid else [],
            asks=[(ask, ask_size)] if ask else [],
            pair=pair,
        )

    async def get_price(self, pair: str) -> float:
        book = await self.get_orderbook(pair, depth=1)
        if book.best_bid and book.best_ask:
            return book.mid_price
        return book.best_bid or book.best_ask

    async def get_funding_rate(self, pair: str) -> FundingRate:
        return FundingRate(pair=pair, rate=0.0, annual_rate=0.0, next_funding_time=0, venue=self.name)

    async def get_balance(self) -> Balance:
        trading, _ = self._require_clients()
        account = await asyncio.to_thread(trading.get_account)
        return Balance(
            total_usd=float(getattr(account, "portfolio_value", 0.0)),
            available_usd=float(getattr(account, "buying_power", 0.0)),
            venue=self.name,
        )

    async def get_positions(self) -> list[Position]:
        trading, _ = self._require_clients()
        positions = await asyncio.to_thread(trading.get_all_positions)
        result: list[Position] = []
        for pos in positions:
            qty = float(getattr(pos, "qty", 0.0))
            result.append(
                Position(
                    pair=getattr(pos, "symbol", ""),
                    side=PositionSide.LONG if qty >= 0 else PositionSide.SHORT,
                    size=abs(qty),
                    entry_price=float(getattr(pos, "avg_entry_price", 0.0)),
                    leverage=1.0,
                    unrealized_pnl=float(getattr(pos, "unrealized_pl", 0.0) or 0.0),
                    venue=self.name,
                )
            )
        return result

    async def place_order(
        self,
        pair: str,
        side: OrderSide,
        order_type: OrderType,
        size: float,
        price: float | None = None,
        leverage: int | None = None,
        stop_price: float | None = None,
        take_profit: float | None = None,
        reduce_only: bool = False,
    ) -> Order:
        trading, _ = self._require_clients()
        if leverage not in (None, 1):
            raise ValueError("Alpaca equities connector does not support leverage overrides")
        if stop_price or take_profit:
            raise NotImplementedError("Bracket/stop handling will be added after paper connector validation")

        def _submit():
            from alpaca.trading.enums import OrderSide as AlpacaSide
            from alpaca.trading.enums import TimeInForce
            from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest

            alpaca_side = AlpacaSide.BUY if side == OrderSide.BUY else AlpacaSide.SELL
            if order_type == OrderType.MARKET:
                request = MarketOrderRequest(
                    symbol=pair,
                    qty=size,
                    side=alpaca_side,
                    time_in_force=TimeInForce.DAY,
                )
            elif order_type == OrderType.LIMIT:
                if price is None:
                    raise ValueError("Limit orders require price")
                request = LimitOrderRequest(
                    symbol=pair,
                    qty=size,
                    side=alpaca_side,
                    time_in_force=TimeInForce.DAY,
                    limit_price=price,
                )
            else:
                raise NotImplementedError(f"Unsupported Alpaca order type: {order_type}")
            return trading.submit_order(order_data=request)

        submitted = await asyncio.to_thread(_submit)
        return _to_order(submitted, pair, self.name)

    async def cancel_order(self, order_id: str, pair: str) -> bool:
        trading, _ = self._require_clients()
        await asyncio.to_thread(trading.cancel_order_by_id, order_id)
        return True

    async def cancel_all_orders(self, pair: str | None = None) -> int:
        trading, _ = self._require_clients()
        cancelled = await asyncio.to_thread(trading.cancel_orders)
        return len(cancelled or [])

    async def get_order(self, order_id: str, pair: str) -> Order:
        trading, _ = self._require_clients()
        order = await asyncio.to_thread(trading.get_order_by_id, order_id)
        return _to_order(order, pair, self.name)

    async def _latest_quote(self, pair: str) -> Any:
        _, data = self._require_clients()

        def _fetch():
            from alpaca.data.requests import StockLatestQuoteRequest

            request = StockLatestQuoteRequest(symbol_or_symbols=pair, feed=self.feed)
            result = data.get_stock_latest_quote(request)
            return result[pair] if isinstance(result, dict) else result

        return await asyncio.to_thread(_fetch)


def _to_alpaca_timeframe(timeframe: str, TimeFrame: Any, TimeFrameUnit: Any) -> Any:
    mapped = _TIMEFRAMES.get(timeframe)
    if mapped is None:
        raise ValueError(f"Unsupported Alpaca timeframe: {timeframe}")
    unit, amount = mapped
    return TimeFrame(amount, getattr(TimeFrameUnit, unit))


def _extract_symbol_records(result: Any, symbol: str) -> list[Any]:
    if hasattr(result, "data"):
        data = result.data
        if isinstance(data, dict):
            return list(data.get(symbol, []))
    if isinstance(result, dict):
        return list(result.get(symbol, []))
    return list(result or [])


def _timestamp_ms(value: Any) -> int:
    if value is None:
        return int(time.time() * 1000)
    if isinstance(value, datetime):
        return int(value.timestamp() * 1000)
    if isinstance(value, (int, float)):
        return int(value * 1000 if value < 10_000_000_000 else value)
    return int(time.time() * 1000)


def _to_order(raw: Any, pair: str, venue: str) -> Order:
    status = str(getattr(raw, "status", "pending")).lower()
    side = str(getattr(raw, "side", "buy")).lower()
    order_type = str(getattr(raw, "order_type", getattr(raw, "type", "market"))).lower()
    return Order(
        order_id=str(getattr(raw, "id", "")),
        pair=str(getattr(raw, "symbol", pair)),
        side=OrderSide.SELL if side == "sell" else OrderSide.BUY,
        order_type=OrderType.LIMIT if order_type == "limit" else OrderType.MARKET,
        size=float(getattr(raw, "qty", 0.0) or 0.0),
        price=_optional_float(getattr(raw, "limit_price", None)),
        status=_ORDER_STATUS_MAP.get(status, OrderStatus.PENDING),
        filled_size=float(getattr(raw, "filled_qty", 0.0) or 0.0),
        avg_fill_price=float(getattr(raw, "filled_avg_price", 0.0) or 0.0),
        timestamp=_timestamp_ms(getattr(raw, "submitted_at", None)),
        venue=venue,
        metadata={"raw_status": status},
    )


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


_ORDER_STATUS_MAP = {
    "new": OrderStatus.OPEN,
    "accepted": OrderStatus.OPEN,
    "pending_new": OrderStatus.PENDING,
    "partially_filled": OrderStatus.PARTIAL,
    "filled": OrderStatus.FILLED,
    "canceled": OrderStatus.CANCELLED,
    "cancelled": OrderStatus.CANCELLED,
    "expired": OrderStatus.CANCELLED,
    "rejected": OrderStatus.REJECTED,
}
