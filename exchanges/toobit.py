"""
Toobit Exchange Connector
Uses CCXT (added official Toobit support Nov 2025) for clean integration.
pip install ccxt

⚠️  US RESTRICTION WARNING:
Toobit is registered in the Cayman Islands with no FinCEN MSB registration.
US residents are explicitly blocked per their Terms of Service.
If you are based in the US, use Hyperliquid or Lighter.xyz instead.
Toobit is included here for non-US users or as a reference implementation.

Docs: https://toobit-docs.github.io/apidocs/usdt_swap/v1/en/
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from .base import (
    Balance, BaseExchange, Candle, FundingRate, Order, OrderBook,
    OrderSide, OrderStatus, OrderType, Position, PositionSide,
)

log = logging.getLogger("apex.toobit")

TIMEFRAME_MAP = {
    "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m",
    "30m": "30m", "1h": "1h", "2h": "2h", "4h": "4h",
    "6h": "6h", "12h": "12h", "1d": "1d", "1w": "1w",
}


class ToobitExchange(BaseExchange):
    name = "toobit"

    def __init__(self, config: dict):
        super().__init__(config)
        self.api_key: str = config.get("api_key", "")
        self.api_secret: str = config.get("api_secret", "")
        self.mode: str = config.get("mode", "futures")
        self._exchange = None   # ccxt.toobit instance

    # ── Lifecycle ────────────────────────────────────────

    async def connect(self) -> None:
        try:
            import ccxt.async_support as ccxt
            self._exchange = ccxt.toobit({
                "apiKey": self.api_key,
                "secret": self.api_secret,
                "options": {
                    "defaultType": "swap" if self.mode == "futures" else "spot",
                },
            })
            await self._exchange.load_markets()
            log.info("Toobit connected via CCXT (mode=%s)", self.mode)
        except ImportError:
            log.warning("ccxt not installed. Run: pip install ccxt")
        except Exception as e:
            log.error("Toobit connect error: %s", e)

    async def disconnect(self) -> None:
        if self._exchange:
            await self._exchange.close()
            self._exchange = None
        log.info("Toobit disconnected")

    # ── Market Data ──────────────────────────────────────

    async def get_candles(self, pair: str, timeframe: str, limit: int = 200) -> list[Candle]:
        if not self._exchange:
            return []
        try:
            tf = TIMEFRAME_MAP.get(timeframe, "5m")
            # CCXT uses BTC/USDT:USDT format for perps
            symbol = self._to_ccxt_symbol(pair)
            raw = await self._exchange.fetch_ohlcv(symbol, tf, limit=limit)
            return [
                Candle(
                    timestamp=int(bar[0]),
                    open=float(bar[1]),
                    high=float(bar[2]),
                    low=float(bar[3]),
                    close=float(bar[4]),
                    volume=float(bar[5]),
                    pair=pair,
                    timeframe=timeframe,
                )
                for bar in raw
            ]
        except Exception as e:
            log.error("Toobit get_candles %s: %s", pair, e)
            return []

    async def get_orderbook(self, pair: str, depth: int = 20) -> OrderBook:
        if not self._exchange:
            return OrderBook(timestamp=0, bids=[], asks=[], pair=pair)
        try:
            symbol = self._to_ccxt_symbol(pair)
            raw = await self._exchange.fetch_order_book(symbol, depth)
            return OrderBook(
                timestamp=int(raw.get("timestamp") or time.time() * 1000),
                bids=[(float(b[0]), float(b[1])) for b in raw.get("bids", [])],
                asks=[(float(a[0]), float(a[1])) for a in raw.get("asks", [])],
                pair=pair,
            )
        except Exception as e:
            log.error("Toobit get_orderbook %s: %s", pair, e)
            return OrderBook(timestamp=0, bids=[], asks=[], pair=pair)

    async def get_price(self, pair: str) -> float:
        if not self._exchange:
            return 0.0
        try:
            symbol = self._to_ccxt_symbol(pair)
            ticker = await self._exchange.fetch_ticker(symbol)
            return float(ticker.get("last") or ticker.get("close") or 0)
        except Exception as e:
            log.error("Toobit get_price %s: %s", pair, e)
            return 0.0

    async def get_funding_rate(self, pair: str) -> FundingRate:
        if not self._exchange:
            return FundingRate(pair=pair, rate=0, annual_rate=0, next_funding_time=0, venue=self.name)
        try:
            symbol = self._to_ccxt_symbol(pair)
            raw = await self._exchange.fetch_funding_rate(symbol)
            rate = float(raw.get("fundingRate", 0))
            annual = rate * 3 * 365 * 100   # 3 funding events/day × 365 days × 100 for %
            return FundingRate(
                pair=pair,
                rate=rate,
                annual_rate=annual,
                next_funding_time=int(raw.get("nextFundingDatetime") or 0),
                venue=self.name,
            )
        except Exception as e:
            log.debug("Toobit get_funding_rate %s: %s", pair, e)
            return FundingRate(pair=pair, rate=0, annual_rate=0, next_funding_time=0, venue=self.name)

    # ── Account ──────────────────────────────────────────

    async def get_balance(self) -> Balance:
        if not self._exchange:
            return Balance(total_usd=0, available_usd=0, venue=self.name)
        try:
            raw = await self._exchange.fetch_balance()
            usdt = raw.get("USDT", {})
            total = float(usdt.get("total", 0) or 0)
            free = float(usdt.get("free", 0) or 0)
            return Balance(total_usd=total, available_usd=free, venue=self.name)
        except Exception as e:
            log.error("Toobit get_balance: %s", e)
            return Balance(total_usd=0, available_usd=0, venue=self.name)

    async def get_positions(self) -> list[Position]:
        if not self._exchange:
            return []
        try:
            raw = await self._exchange.fetch_positions()
            positions = []
            for p in raw:
                size = float(p.get("contracts", 0) or 0)
                if size == 0:
                    continue
                side_str = p.get("side", "long")
                side = PositionSide.LONG if side_str == "long" else PositionSide.SHORT
                positions.append(Position(
                    pair=p.get("symbol", ""),
                    side=side,
                    size=abs(size),
                    entry_price=float(p.get("entryPrice", 0) or 0),
                    leverage=float(p.get("leverage", 1) or 1),
                    unrealized_pnl=float(p.get("unrealizedPnl", 0) or 0),
                    liquidation_price=float(p.get("liquidationPrice", 0) or 0),
                    venue=self.name,
                ))
            return positions
        except Exception as e:
            log.error("Toobit get_positions: %s", e)
            return []

    # ── Order Management ─────────────────────────────────

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
        if not self._exchange:
            raise RuntimeError("Toobit not connected")

        symbol = self._to_ccxt_symbol(pair)

        if leverage:
            try:
                await self._exchange.set_leverage(leverage, symbol)
            except Exception as e:
                log.debug("set_leverage: %s", e)

        ccxt_type = {
            OrderType.MARKET: "market",
            OrderType.LIMIT: "limit",
            OrderType.STOP_MARKET: "stop_market",
            OrderType.STOP_LIMIT: "stop",
        }.get(order_type, "market")

        params: dict = {}
        if reduce_only:
            params["reduceOnly"] = True
        if stop_price:
            params["stopPrice"] = stop_price

        try:
            raw = await self._exchange.create_order(
                symbol, ccxt_type, side.value, size, price, params
            )
            return self._parse_ccxt_order(raw, pair)
        except Exception as e:
            log.error("Toobit place_order %s: %s", pair, e)
            return Order(
                order_id="", pair=pair, side=side, order_type=order_type,
                size=size, price=price, status=OrderStatus.REJECTED, venue=self.name,
            )

    async def cancel_order(self, order_id: str, pair: str) -> bool:
        if not self._exchange:
            return False
        try:
            symbol = self._to_ccxt_symbol(pair)
            await self._exchange.cancel_order(order_id, symbol)
            return True
        except Exception as e:
            log.warning("Toobit cancel_order: %s", e)
            return False

    async def cancel_all_orders(self, pair: str | None = None) -> int:
        if not self._exchange:
            return 0
        try:
            symbol = self._to_ccxt_symbol(pair) if pair else None
            result = await self._exchange.cancel_all_orders(symbol)
            return len(result) if isinstance(result, list) else 1
        except Exception as e:
            log.warning("Toobit cancel_all_orders: %s", e)
            return 0

    async def get_order(self, order_id: str, pair: str) -> Order:
        if not self._exchange:
            return Order(order_id=order_id, pair=pair, side=OrderSide.BUY,
                         order_type=OrderType.MARKET, size=0, price=None,
                         status=OrderStatus.REJECTED, venue=self.name)
        try:
            symbol = self._to_ccxt_symbol(pair)
            raw = await self._exchange.fetch_order(order_id, symbol)
            return self._parse_ccxt_order(raw, pair)
        except Exception as e:
            log.error("Toobit get_order: %s", e)
            return Order(order_id=order_id, pair=pair, side=OrderSide.BUY,
                         order_type=OrderType.MARKET, size=0, price=None,
                         status=OrderStatus.REJECTED, venue=self.name)

    # ── Private helpers ───────────────────────────────────

    def _to_ccxt_symbol(self, pair: str) -> str:
        """
        Convert BTCUSDT → BTC/USDT:USDT (CCXT unified symbol for perpetual swaps).
        For spot: BTCUSDT → BTC/USDT
        """
        if pair.endswith("USDT"):
            base = pair[:-4]
            if self.mode == "futures":
                return f"{base}/USDT:USDT"
            return f"{base}/USDT"
        if pair.endswith("USDC"):
            base = pair[:-4]
            return f"{base}/USDC:USDC" if self.mode == "futures" else f"{base}/USDC"
        return pair

    def _parse_ccxt_order(self, raw: dict, pair: str) -> Order:
        status_map = {
            "open": OrderStatus.OPEN,
            "closed": OrderStatus.FILLED,
            "canceled": OrderStatus.CANCELLED,
            "rejected": OrderStatus.REJECTED,
            "partially_filled": OrderStatus.PARTIAL,
        }
        return Order(
            order_id=str(raw.get("id", "")),
            pair=pair,
            side=OrderSide(raw.get("side", "buy")),
            order_type=OrderType.MARKET if raw.get("type") == "market" else OrderType.LIMIT,
            size=float(raw.get("amount", 0) or 0),
            price=float(raw.get("price", 0) or 0) or None,
            status=status_map.get(raw.get("status", "open"), OrderStatus.OPEN),
            filled_size=float(raw.get("filled", 0) or 0),
            avg_fill_price=float(raw.get("average", 0) or 0),
            timestamp=int(raw.get("timestamp") or time.time() * 1000),
            venue=self.name,
        )
