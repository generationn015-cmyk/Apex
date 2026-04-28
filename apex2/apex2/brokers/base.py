"""Broker abstraction. All brokers (Alpaca, IBKR, CCXT) implement this."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(str, Enum):
    NEW = "new"
    OPEN = "open"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELED = "canceled"
    REJECTED = "rejected"


@dataclass
class Order:
    id: str
    symbol: str
    side: OrderSide
    qty: float
    order_type: OrderType
    status: OrderStatus
    filled_qty: float = 0.0
    avg_fill_price: float | None = None
    limit_price: float | None = None
    stop_price: float | None = None
    submitted_at: datetime | None = None


@dataclass
class Position:
    symbol: str
    qty: float
    avg_entry_price: float
    market_value: float
    unrealized_pl: float


@dataclass
class Account:
    cash: float
    equity: float
    buying_power: float
    portfolio_value: float


class BaseBroker(ABC):
    name: str = "base"

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def get_account(self) -> Account: ...

    @abstractmethod
    async def get_positions(self) -> list[Position]: ...

    @abstractmethod
    async def submit_order(
        self,
        symbol: str,
        side: OrderSide,
        qty: float,
        order_type: OrderType = OrderType.MARKET,
        limit_price: float | None = None,
        stop_price: float | None = None,
        time_in_force: str = "day",
    ) -> Order: ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool: ...

    @abstractmethod
    async def get_order(self, order_id: str) -> Order: ...

    @abstractmethod
    async def is_market_open(self) -> bool: ...
