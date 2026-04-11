"""
Mock Exchange — Demo Mode
=========================
Generates realistic synthetic price data using a random walk so the
full bot pipeline (strategies → signals → confluence → execution →
dashboard) runs without any real API keys or internet access.

Starting prices are approximate April 2026 market values:
  BTC: $85,000  ETH: $2,400  SOL: $135  XRP: $0.52  DOGE: $0.18

Price walk: ±0.3% per tick, with a small momentum carry and mean
reversion so charts look believable rather than pure noise.

This is for demo / paper testing only. Never used in live mode.
"""
from __future__ import annotations

import logging
import math
import random
import time
from typing import Optional

from .base import (
    Balance, BaseExchange, Candle, FundingRate, Order, OrderBook,
    OrderSide, OrderStatus, OrderType, Position, PositionSide,
)

log = logging.getLogger("apex.mock")

# Current approximate prices for April 2026
_SEED_PRICES: dict[str, float] = {
    "BTC":  85_000.0,
    "ETH":   2_400.0,
    "SOL":     135.0,
    "XRP":       0.52,
    "DOGE":      0.185,
}

# Realistic daily-vol percentages (annualized ~60-120%)
_DAILY_VOL: dict[str, float] = {
    "BTC": 0.025,
    "ETH": 0.030,
    "SOL": 0.040,
    "XRP": 0.035,
    "DOGE": 0.045,
}

_CANDLE_SECONDS = {
    "1m": 60, "3m": 180, "5m": 300, "15m": 900,
    "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400,
}


class MockExchange(BaseExchange):
    """
    Synthetic exchange for demo/paper testing.
    Prices walk randomly; orders always fill instantly at current price.
    """
    name = "mock"

    def __init__(self, config: dict | None = None):
        super().__init__(config or {"enabled": True})
        self._prices: dict[str, float] = dict(_SEED_PRICES)
        self._momentum: dict[str, float] = {p: 0.0 for p in _SEED_PRICES}
        self._last_tick: float = time.time()
        self._order_counter = 0
        self._balance = 500.0          # Paper starting balance
        self._positions: list[Position] = []
        self._candle_cache: dict[str, list[Candle]] = {}
        self._funding_rates: dict[str, float] = {
            "BTC": 0.0002, "ETH": 0.0003, "SOL": 0.0004,
            "XRP": 0.0005, "DOGE": 0.0006,
        }
        log.info("Mock exchange initialized — demo mode active")

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def connect(self) -> None:
        log.info("[MOCK] Exchange connected — synthetic prices active")

    async def disconnect(self) -> None:
        log.info("[MOCK] Exchange disconnected")

    # ── Price engine ──────────────────────────────────────────────────

    def _tick_prices(self) -> None:
        """Advance prices by a random walk step (called on each price request)."""
        now = time.time()
        dt  = min(now - self._last_tick, 30.0)  # cap at 30s of accumulated drift
        self._last_tick = now

        for pair in list(self._prices.keys()):
            vol    = _DAILY_VOL.get(pair, 0.03)
            sigma  = vol * math.sqrt(dt / 86400)  # scale daily vol to elapsed seconds
            shock  = random.gauss(0, sigma)
            # Momentum carry (slight mean reversion + trend)
            self._momentum[pair] = 0.92 * self._momentum[pair] + 0.08 * shock
            drift  = self._momentum[pair] * 0.5 + shock * 0.5
            self._prices[pair] *= (1 + drift)
            # Floor at 10% of seed to prevent collapse
            floor  = _SEED_PRICES[pair] * 0.10
            self._prices[pair] = max(self._prices[pair], floor)

    # ── Market data ───────────────────────────────────────────────────

    async def get_price(self, pair: str) -> float:
        self._tick_prices()
        return self._prices.get(pair, 0.0)

    async def get_candles(self, pair: str, timeframe: str, limit: int = 200) -> list[Candle]:
        """
        Build synthetic OHLCV history using a random walk backward from
        the current price.  Cached per (pair, timeframe) and extended each
        call so indicators get fresh bars.
        """
        self._tick_prices()
        current = self._prices.get(pair, 1.0)
        interval = _CANDLE_SECONDS.get(timeframe, 300)
        vol      = _DAILY_VOL.get(pair, 0.03)
        sigma    = vol * math.sqrt(interval / 86400)

        cache_key = f"{pair}:{timeframe}"
        if cache_key not in self._candle_cache:
            # Generate fresh history
            candles = _generate_candle_history(current, limit + 10, interval, sigma)
            self._candle_cache[cache_key] = candles
        else:
            # Append a new candle if enough time has passed
            existing = self._candle_cache[cache_key]
            last_ts  = existing[-1].timestamp
            if time.time() * 1000 - last_ts > interval * 1000 * 0.5:
                prev_close = existing[-1].close
                new_c = _make_candle(prev_close, interval, sigma, pair, timeframe)
                existing.append(new_c)
                if len(existing) > limit + 50:
                    existing.pop(0)

        return self._candle_cache[cache_key][-limit:]

    async def get_orderbook(self, pair: str, depth: int = 20) -> OrderBook:
        self._tick_prices()
        mid   = self._prices.get(pair, 1.0)
        spread = mid * 0.0002   # 0.02% spread
        bids  = [(round(mid - spread * (1 + i * 0.1), 6), random.uniform(0.5, 5.0))
                 for i in range(depth)]
        asks  = [(round(mid + spread * (1 + i * 0.1), 6), random.uniform(0.5, 5.0))
                 for i in range(depth)]
        # Introduce a slight buy or sell imbalance randomly
        imbalance_shift = random.uniform(-0.3, 0.3)
        if imbalance_shift > 0:
            for i in range(len(bids)):
                bids[i] = (bids[i][0], bids[i][1] * (1 + imbalance_shift))
        else:
            for i in range(len(asks)):
                asks[i] = (asks[i][0], asks[i][1] * (1 + abs(imbalance_shift)))
        return OrderBook(
            timestamp=int(time.time() * 1000),
            bids=bids, asks=asks, pair=pair,
        )

    async def get_funding_rate(self, pair: str) -> FundingRate:
        base_rate = self._funding_rates.get(pair, 0.0002)
        # Vary funding by ±50% to simulate market conditions
        rate = base_rate * random.uniform(0.5, 1.8)
        annual = rate * 3 * 365 * 100
        return FundingRate(
            pair=pair, rate=rate, annual_rate=annual,
            next_funding_time=int(time.time()) + 3600,
            venue=self.name,
        )

    # ── Account ───────────────────────────────────────────────────────

    async def get_balance(self) -> Balance:
        return Balance(
            total_usd=self._balance,
            available_usd=self._balance,
            venue=self.name,
        )

    async def get_positions(self) -> list[Position]:
        return list(self._positions)

    # ── Orders (instant fill in demo mode) ───────────────────────────

    async def place_order(
        self,
        pair: str,
        side: OrderSide,
        order_type: OrderType,
        size: float,
        price: Optional[float] = None,
        leverage: Optional[int] = None,
        stop_price: Optional[float] = None,
        take_profit: Optional[float] = None,
        reduce_only: bool = False,
    ) -> Order:
        self._order_counter += 1
        fill_price = price or await self.get_price(pair)
        oid = f"MOCK-{int(time.time())}-{self._order_counter:04d}"
        return Order(
            order_id=oid,
            pair=pair,
            side=side,
            order_type=order_type,
            size=size,
            price=fill_price,
            status=OrderStatus.FILLED,
            filled_size=size,
            avg_fill_price=fill_price,
            timestamp=int(time.time() * 1000),
            venue=self.name,
        )

    async def cancel_order(self, order_id: str, pair: str) -> bool:
        return True

    async def cancel_all_orders(self, pair: str | None = None) -> int:
        return 0

    async def get_order(self, order_id: str, pair: str) -> Order:
        # All mock orders are immediately filled
        return Order(
            order_id=order_id, pair=pair,
            side=OrderSide.BUY, order_type=OrderType.MARKET,
            size=0, price=None,
            status=OrderStatus.FILLED,
            timestamp=int(time.time() * 1000),
            venue=self.name,
        )


# ── Candle generation helpers ─────────────────────────────────────────────

def _make_candle(
    prev_close: float, interval_sec: int, sigma: float, pair: str, timeframe: str
) -> Candle:
    o   = prev_close
    num = max(1, int(interval_sec / 60))
    closes = [o]
    for _ in range(num - 1):
        closes.append(closes[-1] * (1 + random.gauss(0, sigma / math.sqrt(num))))
    c = closes[-1]
    h = max(o, c) * (1 + abs(random.gauss(0, sigma * 0.3)))
    l = min(o, c) * (1 - abs(random.gauss(0, sigma * 0.3)))
    vol = abs(random.gauss(1.0, 0.5)) * 100  # Arbitrary volume units
    return Candle(
        timestamp=int(time.time() * 1000),
        open=round(o, 6), high=round(h, 6),
        low=round(l, 6), close=round(c, 6),
        volume=round(vol, 2), pair=pair, timeframe=timeframe,
    )


def _generate_candle_history(
    current_price: float, count: int, interval_sec: int, sigma: float,
    pair: str = "", timeframe: str = ""
) -> list[Candle]:
    """Walk backward from current_price to generate `count` historical candles."""
    # First build a price series walking backward
    prices = [current_price]
    for _ in range(count - 1):
        prev = prices[-1] / (1 + random.gauss(0, sigma))
        prices.append(max(prev, current_price * 0.01))
    prices.reverse()  # oldest first

    now_ms = int(time.time() * 1000)
    candles = []
    for i, close in enumerate(prices):
        ts     = now_ms - (count - 1 - i) * interval_sec * 1000
        o      = prices[i - 1] if i > 0 else close
        h      = max(o, close) * (1 + abs(random.gauss(0, sigma * 0.3)))
        l      = min(o, close) * (1 - abs(random.gauss(0, sigma * 0.3)))
        vol    = abs(random.gauss(1.0, 0.5)) * 100
        candles.append(Candle(
            timestamp=ts,
            open=round(o, 6), high=round(h, 6),
            low=round(l, 6), close=round(close, 6),
            volume=round(vol, 2), pair=pair, timeframe=timeframe,
        ))
    return candles
