"""
Abstract base class for all exchange connectors.
Every exchange must implement this interface so the bot brain
can route orders to any venue without caring about specifics.
"""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP_MARKET = "stop_market"
    STOP_LIMIT = "stop_limit"


class OrderStatus(str, Enum):
    PENDING = "pending"
    OPEN = "open"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class PositionSide(str, Enum):
    LONG = "long"
    SHORT = "short"


@dataclass
class Candle:
    timestamp: int          # Unix ms
    open: float
    high: float
    low: float
    close: float
    volume: float
    pair: str
    timeframe: str


@dataclass
class OrderBook:
    timestamp: int
    bids: list[tuple[float, float]]   # [(price, size), ...]
    asks: list[tuple[float, float]]
    pair: str

    @property
    def best_bid(self) -> float:
        return self.bids[0][0] if self.bids else 0.0

    @property
    def best_ask(self) -> float:
        return self.asks[0][0] if self.asks else 0.0

    @property
    def mid_price(self) -> float:
        return (self.best_bid + self.best_ask) / 2

    @property
    def spread_pct(self) -> float:
        if self.best_bid == 0:
            return 0.0
        return (self.best_ask - self.best_bid) / self.best_bid * 100

    def imbalance(self, depth: int = 5) -> float:
        """
        Order book imbalance: +1.0 = all bids, -1.0 = all asks.
        Positive = buying pressure, negative = selling pressure.
        """
        bid_vol = sum(s for _, s in self.bids[:depth])
        ask_vol = sum(s for _, s in self.asks[:depth])
        total = bid_vol + ask_vol
        if total == 0:
            return 0.0
        return (bid_vol - ask_vol) / total


@dataclass
class Position:
    pair: str
    side: PositionSide
    size: float
    entry_price: float
    leverage: float
    unrealized_pnl: float = 0.0
    liquidation_price: float = 0.0
    venue: str = ""


@dataclass
class Order:
    order_id: str
    pair: str
    side: OrderSide
    order_type: OrderType
    size: float
    price: float | None
    status: OrderStatus = OrderStatus.PENDING
    filled_size: float = 0.0
    avg_fill_price: float = 0.0
    timestamp: int = 0
    venue: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class FundingRate:
    pair: str
    rate: float           # Current rate (per 8h for most exchanges)
    annual_rate: float    # Annualized (rate * 3 * 365)
    next_funding_time: int
    venue: str


@dataclass
class Balance:
    total_usd: float
    available_usd: float
    venue: str


class BaseExchange(ABC):
    """
    Abstract interface all exchange connectors must implement.
    """

    name: str = "base"

    def __init__(self, config: dict):
        self.config = config
        self._running = False
        self._ws_task: asyncio.Task | None = None

    # ── Lifecycle ────────────────────────────────────────

    @abstractmethod
    async def connect(self) -> None:
        """Initialize connections (REST session, WebSocket)."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Close all connections cleanly."""

    # ── Market Data ──────────────────────────────────────

    @abstractmethod
    async def get_candles(
        self, pair: str, timeframe: str, limit: int = 200
    ) -> list[Candle]:
        """Fetch OHLCV candles."""

    @abstractmethod
    async def get_orderbook(self, pair: str, depth: int = 20) -> OrderBook:
        """Fetch current order book."""

    @abstractmethod
    async def get_price(self, pair: str) -> float:
        """Get current mid price."""

    @abstractmethod
    async def get_funding_rate(self, pair: str) -> FundingRate:
        """Get current funding rate (perpetuals only)."""

    # ── Account ──────────────────────────────────────────

    @abstractmethod
    async def get_balance(self) -> Balance:
        """Get account balance."""

    @abstractmethod
    async def get_positions(self) -> list[Position]:
        """Get all open positions."""

    # ── Order Management ─────────────────────────────────

    @abstractmethod
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
        """Place an order. Returns filled/pending Order."""

    @abstractmethod
    async def cancel_order(self, order_id: str, pair: str) -> bool:
        """Cancel an open order."""

    @abstractmethod
    async def cancel_all_orders(self, pair: str | None = None) -> int:
        """Cancel all open orders. Returns count cancelled."""

    @abstractmethod
    async def get_order(self, order_id: str, pair: str) -> Order:
        """Get order status by ID."""

    # ── Convenience helpers ──────────────────────────────

    async def place_market_order(
        self, pair: str, side: OrderSide, size: float, leverage: int | None = None
    ) -> Order:
        return await self.place_order(
            pair=pair, side=side, order_type=OrderType.MARKET,
            size=size, leverage=leverage
        )

    async def close_position(self, position: Position) -> Order:
        """Close a position by placing a reduce-only market order."""
        close_side = OrderSide.SELL if position.side == PositionSide.LONG else OrderSide.BUY
        return await self.place_order(
            pair=position.pair,
            side=close_side,
            order_type=OrderType.MARKET,
            size=position.size,
            reduce_only=True,
        )
