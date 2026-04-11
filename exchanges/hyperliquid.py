"""
Hyperliquid Exchange Connector
Wraps the official hyperliquid-python-sdk.
No gas fees, native L1, best perpetuals DEX as of 2026.
SDK: pip install hyperliquid-python-sdk
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

log = logging.getLogger("apex.hyperliquid")

# Timeframe → interval string for Hyperliquid API
TF_MAP = {
    "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m",
    "30m": "30m", "1h": "1h", "4h": "4h", "1d": "1d",
}


class HyperliquidExchange(BaseExchange):
    name = "hyperliquid"

    def __init__(self, config: dict):
        super().__init__(config)
        self.wallet_address: str = config.get("wallet_address", "")
        self.private_key: str = config.get("private_key", "")
        self.mainnet: bool = config.get("mainnet", True)
        self._info = None      # hyperliquid.Info
        self._exchange = None  # hyperliquid.Exchange
        self._meta: dict = {}

    # ── Lifecycle ────────────────────────────────────────

    async def connect(self) -> None:
        try:
            from hyperliquid.info import Info
            from hyperliquid.exchange import Exchange
            from hyperliquid.utils import constants

            base_url = constants.MAINNET_API_URL if self.mainnet else constants.TESTNET_API_URL
            self._info = Info(base_url, skip_ws=True)
            self._meta = self._info.meta()

            if self.private_key:
                from eth_account import Account
                account = Account.from_key(self.private_key)
                self._exchange = Exchange(account, base_url)

            log.info("Hyperliquid connected (mainnet=%s)", self.mainnet)
        except ImportError:
            log.warning("hyperliquid-python-sdk not installed. Run: pip install hyperliquid-python-sdk")

    async def disconnect(self) -> None:
        self._info = None
        self._exchange = None
        log.info("Hyperliquid disconnected")

    # ── Market Data ──────────────────────────────────────

    async def get_candles(self, pair: str, timeframe: str, limit: int = 200) -> list[Candle]:
        if not self._info:
            return []
        tf = TF_MAP.get(timeframe, "5m")
        end_ms = int(time.time() * 1000)
        tf_ms = {
            "1m": 60_000, "3m": 180_000, "5m": 300_000,
            "15m": 900_000, "30m": 1_800_000,
            "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000,
        }
        start_ms = end_ms - tf_ms.get(tf, 300_000) * limit

        loop = asyncio.get_event_loop()
        raw = await loop.run_in_executor(
            None,
            lambda: self._info.candles_snapshot(pair, tf, start_ms, end_ms)
        )
        candles = []
        for c in raw:
            candles.append(Candle(
                timestamp=int(c.get("t", 0)),
                open=float(c.get("o", 0)),
                high=float(c.get("h", 0)),
                low=float(c.get("l", 0)),
                close=float(c.get("c", 0)),
                volume=float(c.get("v", 0)),
                pair=pair,
                timeframe=timeframe,
            ))
        return candles

    async def get_orderbook(self, pair: str, depth: int = 20) -> OrderBook:
        if not self._info:
            return OrderBook(timestamp=0, bids=[], asks=[], pair=pair)
        loop = asyncio.get_event_loop()
        raw = await loop.run_in_executor(None, lambda: self._info.l2_snapshot(pair))
        levels = raw.get("levels", [[], []])
        bids = [(float(b["px"]), float(b["sz"])) for b in levels[0][:depth]]
        asks = [(float(a["px"]), float(a["sz"])) for a in levels[1][:depth]]
        return OrderBook(
            timestamp=int(time.time() * 1000),
            bids=bids,
            asks=asks,
            pair=pair,
        )

    async def get_price(self, pair: str) -> float:
        if not self._info:
            return 0.0
        loop = asyncio.get_event_loop()
        mids = await loop.run_in_executor(None, self._info.all_mids)
        return float(mids.get(pair, 0))

    async def get_funding_rate(self, pair: str) -> FundingRate:
        if not self._info:
            return FundingRate(pair=pair, rate=0, annual_rate=0, next_funding_time=0, venue=self.name)
        loop = asyncio.get_event_loop()
        raw = await loop.run_in_executor(None, self._info.funding_history, pair, int(time.time() * 1000) - 3_600_000, None)
        if raw:
            latest = raw[-1]
            rate = float(latest.get("fundingRate", 0))
            annual = rate * 3 * 365 * 100
            return FundingRate(
                pair=pair, rate=rate, annual_rate=annual,
                next_funding_time=0, venue=self.name,
            )
        return FundingRate(pair=pair, rate=0, annual_rate=0, next_funding_time=0, venue=self.name)

    # ── Account ──────────────────────────────────────────

    async def get_balance(self) -> Balance:
        if not self._info or not self.wallet_address:
            return Balance(total_usd=0, available_usd=0, venue=self.name)
        loop = asyncio.get_event_loop()
        state = await loop.run_in_executor(
            None, lambda: self._info.user_state(self.wallet_address)
        )
        margin = state.get("marginSummary", {})
        total = float(margin.get("accountValue", 0))
        available = float(state.get("withdrawable", total))
        return Balance(total_usd=total, available_usd=available, venue=self.name)

    async def get_positions(self) -> list[Position]:
        if not self._info or not self.wallet_address:
            return []
        loop = asyncio.get_event_loop()
        state = await loop.run_in_executor(
            None, lambda: self._info.user_state(self.wallet_address)
        )
        positions = []
        for p in state.get("assetPositions", []):
            pos = p.get("position", {})
            szi = float(pos.get("szi", 0))
            if szi == 0:
                continue
            side = PositionSide.LONG if szi > 0 else PositionSide.SHORT
            positions.append(Position(
                pair=pos.get("coin", ""),
                side=side,
                size=abs(szi),
                entry_price=float(pos.get("entryPx", 0)),
                leverage=float(pos.get("leverage", {}).get("value", 1)),
                unrealized_pnl=float(pos.get("unrealizedPnl", 0)),
                liquidation_price=float(pos.get("liquidationPx", 0) or 0),
                venue=self.name,
            ))
        return positions

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
            raise RuntimeError("Hyperliquid: private key not configured")

        is_buy = side == OrderSide.BUY
        is_market = order_type == OrderType.MARKET

        if leverage:
            await self._set_leverage(pair, leverage)

        # For market orders, use slippage-adjusted limit
        if is_market:
            current_price = await self.get_price(pair)
            slippage = 0.003  # 0.3% slippage tolerance
            limit_px = current_price * (1 + slippage) if is_buy else current_price * (1 - slippage)
            order_is_limit = True
        else:
            limit_px = price
            order_is_limit = True

        order_type_hl = {"limit": {"tif": "Ioc" if is_market else "Gtc"}}

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self._exchange.order(
                pair, is_buy, size, round(limit_px, 2),
                order_type_hl, reduce_only=reduce_only
            )
        )
        return self._parse_hl_result(result, pair, side, size, limit_px)

    async def cancel_order(self, order_id: str, pair: str) -> bool:
        if not self._exchange:
            return False
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                None, lambda: self._exchange.cancel(pair, int(order_id))
            )
            return True
        except Exception as e:
            log.warning("HL cancel_order: %s", e)
            return False

    async def cancel_all_orders(self, pair: str | None = None) -> int:
        if not self._info or not self.wallet_address:
            return 0
        loop = asyncio.get_event_loop()
        open_orders = await loop.run_in_executor(
            None, lambda: self._info.open_orders(self.wallet_address)
        )
        count = 0
        for o in open_orders:
            if pair and o.get("coin") != pair:
                continue
            if await self.cancel_order(str(o.get("oid")), o.get("coin")):
                count += 1
        return count

    async def get_order(self, order_id: str, pair: str) -> Order:
        if not self._info or not self.wallet_address:
            return Order(order_id=order_id, pair=pair, side=OrderSide.BUY,
                         order_type=OrderType.MARKET, size=0, price=None,
                         status=OrderStatus.REJECTED, venue=self.name)
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(
            None, lambda: self._info.query_order_by_oid(self.wallet_address, int(order_id))
        )
        return self._parse_hl_order(data.get("order", {}))

    # ── Private helpers ───────────────────────────────────

    async def _set_leverage(self, pair: str, leverage: int) -> None:
        if not self._exchange:
            return
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                None, lambda: self._exchange.update_leverage(leverage, pair)
            )
        except Exception as e:
            log.debug("HL set_leverage: %s", e)

    def _parse_hl_result(self, result: dict, pair: str, side: OrderSide, size: float, price: float) -> Order:
        status_data = result.get("response", {}).get("data", {})
        statuses = status_data.get("statuses", [{}])
        first = statuses[0] if statuses else {}
        if "filled" in first:
            filled = first["filled"]
            return Order(
                order_id=str(filled.get("oid", "")),
                pair=pair, side=side, order_type=OrderType.MARKET,
                size=size, price=price,
                status=OrderStatus.FILLED,
                filled_size=float(filled.get("totalSz", size)),
                avg_fill_price=float(filled.get("avgPx", price)),
                timestamp=int(time.time() * 1000),
                venue=self.name,
            )
        oid = first.get("resting", {}).get("oid", "0")
        return Order(
            order_id=str(oid), pair=pair, side=side,
            order_type=OrderType.LIMIT, size=size, price=price,
            status=OrderStatus.OPEN,
            timestamp=int(time.time() * 1000),
            venue=self.name,
        )

    def _parse_hl_order(self, data: dict) -> Order:
        status_map = {
            "open": OrderStatus.OPEN,
            "filled": OrderStatus.FILLED,
            "canceled": OrderStatus.CANCELLED,
        }
        return Order(
            order_id=str(data.get("oid", "")),
            pair=data.get("coin", ""),
            side=OrderSide.BUY if data.get("isBuy") else OrderSide.SELL,
            order_type=OrderType.LIMIT,
            size=float(data.get("origSz", 0)),
            price=float(data.get("limitPx", 0)),
            status=status_map.get(data.get("status", "open"), OrderStatus.OPEN),
            filled_size=float(data.get("origSz", 0)) - float(data.get("sz", 0)),
            timestamp=int(data.get("timestamp", 0)),
            venue=self.name,
        )
