"""
Lighter.xyz Exchange Connector
Custom ZK rollup (app-specific, not zkSync/Arbitrum), settles to Ethereum L1.
159+ USDC-settled perpetual futures. Zero fees for standard accounts.
SDK: pip install lighter-sdk
Docs: https://apidocs.lighter.xyz

⚠️  US RESTRICTION WARNING:
Lighter.xyz explicitly blocks US residents per their Terms of Service.
Geo-blocking enforced by IP. US persons violate ToS by using this platform.
If you are US-based, use Hyperliquid instead — it has no geo-restrictions.

Authentication notes:
- One-time wallet registration on lighter.xyz
- Create API keys (up to 253 per account) via the UI
- SDK generates short-lived auth tokens from your API private key
- Each transaction must be signed + nonce-managed (SDK handles this)

Market symbols use "-PERP" suffix: BTC-PERP, ETH-PERP, SOL-PERP
WebSocket: wss://mainnet.zklighter.elliot.ai/stream
"""
from __future__ import annotations

import logging
import time

from .base import (
    Balance, BaseExchange, Candle, FundingRate, Order, OrderBook,
    OrderSide, OrderStatus, OrderType, Position, PositionSide,
)

log = logging.getLogger("apex.lighter")


class LighterExchange(BaseExchange):
    name = "lighter"

    def __init__(self, config: dict):
        super().__init__(config)
        self.wallet_address: str = config.get("wallet_address", "")
        self.api_private_key: str = config.get("private_key", "")   # API key, not main wallet key
        self.account_index: int = config.get("account_index", 0)
        self.api_key_index: int = config.get("api_key_index", 2)     # 0,1 reserved for UI
        self.mainnet: bool = config.get("mainnet", True)
        self._client = None      # lighter_sdk client
        self._signer = None      # SignerClient

    # ── Lifecycle ────────────────────────────────────────

    async def connect(self) -> None:
        try:
            from lighter_sdk import create_client, SignerClient, Network

            network = Network.MAINNET if self.mainnet else Network.TESTNET
            self._client = await create_client(network=network)

            if self.api_private_key and self.wallet_address:
                self._signer = SignerClient(
                    client=self._client,
                    account_index=self.account_index,
                    api_key_index=self.api_key_index,
                    api_private_key=self.api_private_key,
                )
                log.info("Lighter.xyz connected with signing (mainnet=%s)", self.mainnet)
            else:
                log.info("Lighter.xyz connected read-only (no API key configured)")

        except ImportError:
            log.warning("lighter-sdk not installed. Run: pip install lighter-sdk")
        except Exception as e:
            log.error("Lighter connect error: %s", e)

    async def disconnect(self) -> None:
        if self._client:
            try:
                await self._client.close()
            except Exception:
                pass
        self._client = None
        self._signer = None
        log.info("Lighter.xyz disconnected")

    # ── Market Data ──────────────────────────────────────

    async def get_candles(self, pair: str, timeframe: str, limit: int = 200) -> list[Candle]:
        if not self._client:
            return []
        try:
            market = self._normalize_pair(pair)
            resolution = self._tf_to_resolution(timeframe)
            raw = await self._client.get_candlesticks(
                market_symbol=market,
                resolution=resolution,
                count=limit,
            )
            candles = []
            for c in (raw or []):
                candles.append(Candle(
                    timestamp=int(c.get("time", 0)) * 1000,
                    open=float(c.get("open", 0)),
                    high=float(c.get("high", 0)),
                    low=float(c.get("low", 0)),
                    close=float(c.get("close", 0)),
                    volume=float(c.get("volume", 0)),
                    pair=pair,
                    timeframe=timeframe,
                ))
            return candles
        except Exception as e:
            log.error("Lighter get_candles %s: %s", pair, e)
            return []

    async def get_orderbook(self, pair: str, depth: int = 20) -> OrderBook:
        if not self._client:
            return OrderBook(timestamp=0, bids=[], asks=[], pair=pair)
        try:
            market = self._normalize_pair(pair)
            raw = await self._client.get_orderbook(market_symbol=market, depth=depth)
            bids = [(float(b["price"]), float(b["quantity"])) for b in raw.get("bids", [])]
            asks = [(float(a["price"]), float(a["quantity"])) for a in raw.get("asks", [])]
            return OrderBook(
                timestamp=int(time.time() * 1000),
                bids=bids, asks=asks, pair=pair,
            )
        except Exception as e:
            log.error("Lighter get_orderbook %s: %s", pair, e)
            return OrderBook(timestamp=0, bids=[], asks=[], pair=pair)

    async def get_price(self, pair: str) -> float:
        ob = await self.get_orderbook(pair, depth=1)
        return ob.mid_price

    async def get_funding_rate(self, pair: str) -> FundingRate:
        """
        Lighter perpetuals use funding rates. Attempting to fetch via SDK.
        If unavailable, returns zero (non-blocking).
        """
        if not self._client:
            return FundingRate(pair=pair, rate=0, annual_rate=0, next_funding_time=0, venue=self.name)
        try:
            market = self._normalize_pair(pair)
            raw = await self._client.get_market(market_symbol=market)
            rate = float(raw.get("fundingRate", 0))
            annual = rate * 3 * 365 * 100
            return FundingRate(
                pair=pair, rate=rate, annual_rate=annual,
                next_funding_time=0, venue=self.name,
            )
        except Exception as e:
            log.debug("Lighter get_funding_rate %s: %s", pair, e)
            return FundingRate(pair=pair, rate=0, annual_rate=0, next_funding_time=0, venue=self.name)

    # ── Account ──────────────────────────────────────────

    async def get_balance(self) -> Balance:
        if not self._client or not self.account_index:
            return Balance(total_usd=0, available_usd=0, venue=self.name)
        try:
            raw = await self._client.get_account(account_index=self.account_index)
            usdc = float(raw.get("collateral", raw.get("usdcBalance", 0)))
            free = float(raw.get("availableCollateral", usdc))
            return Balance(total_usd=usdc, available_usd=free, venue=self.name)
        except Exception as e:
            log.error("Lighter get_balance: %s", e)
            return Balance(total_usd=0, available_usd=0, venue=self.name)

    async def get_positions(self) -> list[Position]:
        if not self._client or not self.account_index:
            return []
        try:
            raw = await self._client.get_open_positions(account_index=self.account_index)
            positions = []
            for p in (raw or []):
                size = float(p.get("size", 0))
                if size == 0:
                    continue
                side = PositionSide.LONG if size > 0 else PositionSide.SHORT
                positions.append(Position(
                    pair=p.get("marketSymbol", ""),
                    side=side,
                    size=abs(size),
                    entry_price=float(p.get("avgEntryPrice", 0)),
                    leverage=float(p.get("leverage", 1)),
                    unrealized_pnl=float(p.get("unrealizedPnl", 0)),
                    liquidation_price=float(p.get("liquidationPrice", 0)),
                    venue=self.name,
                ))
            return positions
        except Exception as e:
            log.error("Lighter get_positions: %s", e)
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
        if not self._signer:
            raise RuntimeError("Lighter: API key not configured (set private_key in config)")

        market = self._normalize_pair(pair)
        is_ask = side == OrderSide.SELL   # Lighter: is_ask=True means sell

        try:
            if order_type == OrderType.MARKET:
                # Use aggressive limit with IOC for market-like execution on Lighter CLOB
                ob = await self.get_orderbook(pair, depth=1)
                slippage = 0.003
                limit_price = ob.best_ask * (1 + slippage) if not is_ask else ob.best_bid * (1 - slippage)
                time_in_force = "IOC"
            else:
                limit_price = price
                time_in_force = "GTC"

            result = await self._signer.create_order(
                market_symbol=market,
                is_ask=is_ask,
                base_amount=str(size),
                price=str(round(limit_price, 6)),
                time_in_force=time_in_force,
                reduce_only=reduce_only,
            )
            order_id = str(result.get("orderId", result.get("order_id", "")))
            return Order(
                order_id=order_id,
                pair=pair, side=side,
                order_type=order_type,
                size=size, price=limit_price,
                status=OrderStatus.OPEN,
                timestamp=int(time.time() * 1000),
                venue=self.name,
            )
        except Exception as e:
            log.error("Lighter place_order %s: %s", pair, e)
            return Order(
                order_id="", pair=pair, side=side,
                order_type=order_type, size=size, price=price,
                status=OrderStatus.REJECTED, venue=self.name,
            )

    async def cancel_order(self, order_id: str, pair: str) -> bool:
        if not self._signer:
            return False
        try:
            market = self._normalize_pair(pair)
            await self._signer.cancel_order(market_symbol=market, order_id=int(order_id))
            return True
        except Exception as e:
            log.warning("Lighter cancel_order: %s", e)
            return False

    async def cancel_all_orders(self, pair: str | None = None) -> int:
        if not self._signer:
            return 0
        try:
            market = self._normalize_pair(pair) if pair else None
            result = await self._signer.cancel_all_orders(market_symbol=market)
            return result.get("count", 0) if isinstance(result, dict) else 0
        except Exception as e:
            log.warning("Lighter cancel_all_orders: %s", e)
            return 0

    async def get_order(self, order_id: str, pair: str) -> Order:
        if not self._client:
            return Order(order_id=order_id, pair=pair, side=OrderSide.BUY,
                         order_type=OrderType.LIMIT, size=0, price=None,
                         status=OrderStatus.REJECTED, venue=self.name)
        try:
            raw = await self._client.get_order(order_id=int(order_id))
            return self._parse_order(raw, pair)
        except Exception as e:
            log.error("Lighter get_order: %s", e)
            return Order(order_id=order_id, pair=pair, side=OrderSide.BUY,
                         order_type=OrderType.LIMIT, size=0, price=None,
                         status=OrderStatus.REJECTED, venue=self.name)

    # ── Private helpers ───────────────────────────────────

    def _normalize_pair(self, pair: str) -> str:
        """
        Convert common pair formats to Lighter's BTC-PERP style.
        BTCUSDT → BTC-PERP
        BTC-USDC → BTC-PERP
        BTC-PERP → BTC-PERP (passthrough)
        """
        pair = pair.replace("USDT", "").replace("USDC", "").replace("/", "").strip("-")
        if not pair.endswith("-PERP"):
            pair = f"{pair}-PERP"
        return pair

    def _tf_to_resolution(self, timeframe: str) -> int:
        """Convert timeframe string to seconds for Lighter candlestick API."""
        return {
            "1m": 60, "5m": 300, "15m": 900,
            "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400,
        }.get(timeframe, 300)

    def _parse_order(self, data: dict, pair: str) -> Order:
        status_map = {
            "open": OrderStatus.OPEN,
            "filled": OrderStatus.FILLED,
            "partially_filled": OrderStatus.PARTIAL,
            "canceled": OrderStatus.CANCELLED,
            "expired": OrderStatus.CANCELLED,
        }
        is_ask = data.get("isAsk", data.get("is_ask", False))
        side = OrderSide.SELL if is_ask else OrderSide.BUY
        return Order(
            order_id=str(data.get("orderId", data.get("order_id", ""))),
            pair=pair, side=side,
            order_type=OrderType.LIMIT,
            size=float(data.get("baseAmount", data.get("size", 0))),
            price=float(data.get("price", 0)),
            status=status_map.get(data.get("status", "open"), OrderStatus.OPEN),
            filled_size=float(data.get("filledAmount", data.get("filled_size", 0))),
            timestamp=int(data.get("createdAt", data.get("created_at", 0))) * 1000,
            venue=self.name,
        )
