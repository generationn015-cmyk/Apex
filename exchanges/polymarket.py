"""
Polymarket Exchange Connector
CLOB-based prediction markets on Polygon (chain ID 137).
SDK: pip install py-clob-client

⚠️  US ACCESS NOTES (April 2026):
- polymarket.com (global) — geoblocked for US residents
- polymarketexchange.com (Polymarket US) — CFTC DCM licensed, launched Dec 3 2025.
  Requires KYC (government ID + SSN). Still invite-only/waitlist as of Q2 2026.
  Full public launch estimated Q3-Q4 2026.
  When available: only 0.01% taker fees vs global's ~1-7% — much better for bots.

Authentication (two-layer):
  L1: Ethereum private key on Polygon (chain_id=137), EIP-712 order signing
  L2: Derived API key/secret/passphrase via create_or_derive_api_creds()
      These are deterministically derived — no separate registration needed.
  Before first trade: approve USDC + Conditional Token allowances (see below)

Fee structure:
  Maker fees: ZERO (+ earn 25% rebate on taker fees you generate)
  Taker fees: fee = category_rate × p × (1 - p) per share
    - Crypto markets: up to ~1.8% (peaks at p=0.50)
    - Sports: up to ~0.75%
    - Politics/Finance: up to ~1.0%
    - Geopolitics: 0%
    → Fees approach ZERO as price → $0.01 or $0.99 (near-resolved markets)

API structure:
  CLOB:  https://clob.polymarket.com       (orders, order book, prices)
  Gamma: https://gamma-api.polymarket.com  (market metadata, events)
  Data:  https://data-api.polymarket.com   (historical trades)
  WS:    wss://ws-subscriptions-clob.polymarket.com
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

log = logging.getLogger("apex.polymarket")

CLOB_URL = "https://clob.polymarket.com"
GAMMA_URL = "https://gamma-api.polymarket.com"
POLYGON_CHAIN_ID = 137


class PolymarketExchange(BaseExchange):
    name = "polymarket"

    def __init__(self, config: dict):
        super().__init__(config)
        self.private_key: str = config.get("wallet_private_key", "")
        self.api_key: str = config.get("api_key", "")
        self.api_secret: str = config.get("api_secret", "")
        self.passphrase: str = config.get("passphrase", "")
        self.min_edge_pct: float = config.get("min_edge_pct", 8.0)
        self._client = None   # ClobClient
        self._markets_cache: list = []
        self._cache_ts: float = 0

    # ── Lifecycle ────────────────────────────────────────

    async def connect(self) -> None:
        try:
            from py_clob_client.client import ClobClient

            self._client = ClobClient(
                host=CLOB_URL,
                key=self.private_key,
                chain_id=POLYGON_CHAIN_ID,
                signature_type=0,   # 0=EOA/hardware wallet, 1=Magic Link
            )

            # Derive API credentials from wallet (deterministic, no registration needed)
            if self.api_key:
                from py_clob_client.clob_types import ApiCreds
                creds = ApiCreds(
                    api_key=self.api_key,
                    api_secret=self.api_secret,
                    api_passphrase=self.passphrase,
                )
                self._client.set_api_creds(creds)
            elif self.private_key:
                # Auto-derive creds from wallet signature
                loop = asyncio.get_event_loop()
                creds = await loop.run_in_executor(
                    None, self._client.create_or_derive_api_creds
                )
                self._client.set_api_creds(creds)
                log.info("Polymarket API creds derived from wallet")

            log.info("Polymarket connected")
        except ImportError:
            log.warning("py-clob-client not installed. Run: pip install py-clob-client")
        except Exception as e:
            log.error("Polymarket connect error: %s", e)

    async def disconnect(self) -> None:
        self._client = None
        log.info("Polymarket disconnected")

    # ── Market Intelligence ──────────────────────────────

    async def get_active_markets(self, category: str | None = None, limit: int = 200) -> list[dict]:
        """
        Fetch active prediction markets from Gamma API.
        Cached for 5 minutes to avoid hammering the API.
        """
        now = time.time()
        if self._markets_cache and (now - self._cache_ts) < 300:
            markets = self._markets_cache
            if category:
                markets = [m for m in markets if m.get("category", "").lower() == category.lower()]
            return markets[:limit]

        try:
            import aiohttp
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                params = {"active": "true", "closed": "false", "limit": str(limit)}
                if category:
                    params["category"] = category
                async with session.get(f"{GAMMA_URL}/markets", params=params) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()

            markets = []
            for m in (data if isinstance(data, list) else data.get("markets", [])):
                tokens = m.get("tokens", [])
                if not tokens:
                    continue
                yes_token = next((t for t in tokens if t.get("outcome") == "Yes"), tokens[0])
                no_token = next((t for t in tokens if t.get("outcome") == "No"), tokens[1] if len(tokens) > 1 else {})
                markets.append({
                    "condition_id": m.get("conditionId", m.get("condition_id", "")),
                    "question": m.get("question", ""),
                    "category": m.get("category", ""),
                    "yes_token_id": yes_token.get("token_id", ""),
                    "no_token_id": no_token.get("token_id", ""),
                    "yes_price": float(yes_token.get("price", 0.5)),
                    "no_price": float(no_token.get("price", 0.5)),
                    "volume_24h": float(m.get("volume24hr", 0)),
                    "end_date": m.get("end_date_iso", ""),
                    "fee_rate": float(m.get("feeRate", 0.04)),
                })

            self._markets_cache = markets
            self._cache_ts = now
            return markets

        except Exception as e:
            log.error("Polymarket get_active_markets: %s", e)
            return []

    async def find_yesno_arb(self) -> list[dict]:
        """
        YES/NO Complementary Arbitrage Scanner.

        On binary markets, YES price + NO price should = $1.00.
        When both sides' ASKS sum to < $1.00 (after fees), buying both
        is risk-free profit — redeem the pair for $1.00.

        This is the #1 automated strategy on Polymarket.
        Avg opportunity: ~2.7 seconds (down from 12.3s in 2024 as bots got faster).

        Returns: list of arb opportunities sorted by profit descending
        """
        if not self._client:
            return []

        markets = await self.get_active_markets(limit=300)
        opps = []

        for m in markets:
            yes_id = m["yes_token_id"]
            no_id = m["no_token_id"]
            if not yes_id or not no_id:
                continue

            try:
                # Get best asks from CLOB order book
                loop = asyncio.get_event_loop()
                yes_book = await loop.run_in_executor(
                    None, lambda: self._client.get_order_book(yes_id)
                )
                no_book = await loop.run_in_executor(
                    None, lambda: self._client.get_order_book(no_id)
                )

                if not yes_book or not no_book:
                    continue

                yes_ask = float(yes_book.asks[0].price) if yes_book.asks else 1.0
                no_ask = float(no_book.asks[0].price) if no_book.asks else 1.0
                total_cost = yes_ask + no_ask

                # Estimate fees (fee = feeRate × p × (1-p) per share)
                fee_rate = m["fee_rate"]
                yes_fee = fee_rate * yes_ask * (1 - yes_ask)
                no_fee = fee_rate * no_ask * (1 - no_ask)
                total_fees = yes_fee + no_fee

                profit = 1.0 - total_cost - total_fees

                if profit > 0.005:   # At least 0.5 cents profit per $1 pair
                    opps.append({
                        **m,
                        "yes_ask": yes_ask,
                        "no_ask": no_ask,
                        "total_cost": round(total_cost, 4),
                        "estimated_fees": round(total_fees, 4),
                        "profit_per_share": round(profit, 4),
                        "profit_pct": round(profit * 100, 2),
                        "arb_type": "yesno_complementary",
                    })

            except Exception as e:
                log.debug("yesno_arb scan %s: %s", m.get("question", "?")[:40], e)
                continue

        opps.sort(key=lambda x: x["profit_per_share"], reverse=True)
        if opps:
            log.info("Found %d YES/NO arb opportunities. Best: %.2f%%", len(opps), opps[0]["profit_pct"])
        return opps

    async def find_edges(self, model_probabilities: dict[str, float]) -> list[dict]:
        """
        Value bet finder: compare model probability to market price.
        Use this when you have an external data source (news, stats, weather API)
        that gives you a better probability estimate than the market.

        model_probabilities: {condition_id: probability_0_to_1}
        Returns markets where |model_prob - market_price| > min_edge_pct
        """
        markets = await self.get_active_markets()
        edges = []
        for m in markets:
            cid = m["condition_id"]
            if cid not in model_probabilities:
                continue
            model_p = model_probabilities[cid]
            market_p = m["yes_price"]
            edge = abs(model_p - market_p) * 100

            if edge >= self.min_edge_pct:
                side = "YES" if model_p > market_p else "NO"
                token_id = m["yes_token_id"] if side == "YES" else m["no_token_id"]
                buy_price = m["yes_price"] if side == "YES" else m["no_price"]
                edges.append({
                    **m,
                    "model_prob": model_p,
                    "market_prob": market_p,
                    "edge_pct": round(edge, 2),
                    "recommended_side": side,
                    "token_id": token_id,
                    "buy_price": buy_price,
                })
        edges.sort(key=lambda x: x["edge_pct"], reverse=True)
        return edges

    # ── Order Management ─────────────────────────────────

    async def place_limit_order(
        self,
        token_id: str,
        side: str,    # "BUY" or "SELL"
        price: float,
        size: float,
        time_in_force: str = "GTC",
    ) -> Order:
        """
        Place a limit order on Polymarket CLOB.
        price: 0.01 – 0.99 (probability cents)
        size: number of shares
        time_in_force: GTC (Good Till Cancelled) or FOK (Fill Or Kill)
        """
        if not self._client:
            raise RuntimeError("Polymarket not connected")
        try:
            from py_clob_client.clob_types import OrderArgs, OrderType as PMOrderType
            from py_clob_client.constants import BUY, SELL

            pm_side = BUY if side == "BUY" else SELL
            order_args = OrderArgs(
                token_id=token_id,
                price=price,
                size=size,
                side=pm_side,
            )
            loop = asyncio.get_event_loop()
            order_obj = await loop.run_in_executor(
                None, lambda: self._client.create_order(order_args)
            )
            pm_type = PMOrderType.GTC if time_in_force == "GTC" else PMOrderType.FOK
            result = await loop.run_in_executor(
                None, lambda: self._client.post_order(order_obj, pm_type)
            )
            order_side = OrderSide.BUY if side == "BUY" else OrderSide.SELL
            return Order(
                order_id=result.get("orderID", result.get("order_id", "")),
                pair=token_id, side=order_side,
                order_type=OrderType.LIMIT,
                size=size, price=price,
                status=OrderStatus.OPEN,
                timestamp=int(time.time() * 1000),
                venue=self.name,
            )
        except Exception as e:
            log.error("Polymarket place_limit_order: %s", e)
            return Order(order_id="", pair=token_id,
                         side=OrderSide.BUY if side == "BUY" else OrderSide.SELL,
                         order_type=OrderType.LIMIT, size=size, price=price,
                         status=OrderStatus.REJECTED, venue=self.name)

    async def place_market_buy(self, token_id: str, amount_usd: float) -> Order:
        """
        Buy $amount_usd worth of a token at market price (FOK).
        """
        if not self._client:
            raise RuntimeError("Polymarket not connected")
        try:
            from py_clob_client.clob_types import MarketOrderArgs, OrderType as PMOrderType
            from py_clob_client.constants import BUY

            order_args = MarketOrderArgs(
                token_id=token_id,
                amount=amount_usd,
                side=BUY,
            )
            loop = asyncio.get_event_loop()
            order_obj = await loop.run_in_executor(
                None, lambda: self._client.create_market_order(order_args)
            )
            result = await loop.run_in_executor(
                None, lambda: self._client.post_order(order_obj, PMOrderType.FOK)
            )
            return Order(
                order_id=result.get("orderID", ""),
                pair=token_id, side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                size=amount_usd, price=None,
                status=OrderStatus.OPEN,
                timestamp=int(time.time() * 1000),
                venue=self.name,
            )
        except Exception as e:
            log.error("Polymarket place_market_buy: %s", e)
            return Order(order_id="", pair=token_id, side=OrderSide.BUY,
                         order_type=OrderType.MARKET, size=amount_usd, price=None,
                         status=OrderStatus.REJECTED, venue=self.name)

    # ── Standard BaseExchange interface ──────────────────

    async def place_order(
        self, pair: str, side: OrderSide, order_type: OrderType, size: float,
        price: float | None = None, leverage: int | None = None,
        stop_price: float | None = None, take_profit: float | None = None,
        reduce_only: bool = False,
    ) -> Order:
        """Generic order placement. For Polymarket, 'pair' = token_id."""
        pm_side = "BUY" if side == OrderSide.BUY else "SELL"
        if order_type == OrderType.MARKET:
            return await self.place_market_buy(pair, size)
        return await self.place_limit_order(pair, pm_side, price or 0.5, size)

    async def cancel_order(self, order_id: str, pair: str) -> bool:
        if not self._client:
            return False
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: self._client.cancel(order_id))
            return True
        except Exception as e:
            log.warning("Polymarket cancel_order: %s", e)
            return False

    async def cancel_all_orders(self, pair: str | None = None) -> int:
        if not self._client:
            return 0
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self._client.cancel_all)
            canceled = result.get("canceled", [])
            return len(canceled) if isinstance(canceled, list) else 0
        except Exception as e:
            log.warning("Polymarket cancel_all_orders: %s", e)
            return 0

    async def get_order(self, order_id: str, pair: str) -> Order:
        if not self._client:
            return Order(order_id=order_id, pair=pair, side=OrderSide.BUY,
                         order_type=OrderType.LIMIT, size=0, price=None,
                         status=OrderStatus.REJECTED, venue=self.name)
        try:
            loop = asyncio.get_event_loop()
            raw = await loop.run_in_executor(
                None, lambda: self._client.get_order(order_id)
            )
            status_map = {
                "LIVE": OrderStatus.OPEN,
                "MATCHED": OrderStatus.FILLED,
                "CANCELED": OrderStatus.CANCELLED,
                "UNMATCHED": OrderStatus.OPEN,
            }
            return Order(
                order_id=order_id,
                pair=raw.get("asset_id", pair),
                side=OrderSide.BUY if raw.get("side") == "BUY" else OrderSide.SELL,
                order_type=OrderType.LIMIT,
                size=float(raw.get("original_size", 0)),
                price=float(raw.get("price", 0)),
                status=status_map.get(raw.get("status", "LIVE"), OrderStatus.OPEN),
                filled_size=float(raw.get("size_matched", 0)),
                timestamp=int(time.time() * 1000),
                venue=self.name,
            )
        except Exception as e:
            log.error("Polymarket get_order: %s", e)
            return Order(order_id=order_id, pair=pair, side=OrderSide.BUY,
                         order_type=OrderType.LIMIT, size=0, price=None,
                         status=OrderStatus.REJECTED, venue=self.name)

    async def get_balance(self) -> Balance:
        if not self._client:
            return Balance(total_usd=0, available_usd=0, venue=self.name)
        try:
            loop = asyncio.get_event_loop()
            bal = await loop.run_in_executor(None, self._client.get_balance)
            amount = float(bal) if isinstance(bal, (int, float, str)) else 0
            return Balance(total_usd=amount, available_usd=amount, venue=self.name)
        except Exception as e:
            log.error("Polymarket get_balance: %s", e)
            return Balance(total_usd=0, available_usd=0, venue=self.name)

    async def get_positions(self) -> list[Position]:
        return []   # Polymarket positions managed separately (conditional tokens)

    # ── Stubs (not applicable for prediction markets) ────

    async def get_candles(self, pair: str, timeframe: str, limit: int = 200) -> list[Candle]:
        return []

    async def get_orderbook(self, pair: str, depth: int = 20) -> OrderBook:
        return OrderBook(timestamp=0, bids=[], asks=[], pair=pair)

    async def get_price(self, pair: str) -> float:
        return 0.0

    async def get_funding_rate(self, pair: str) -> FundingRate:
        return FundingRate(pair=pair, rate=0, annual_rate=0, next_funding_time=0, venue=self.name)
