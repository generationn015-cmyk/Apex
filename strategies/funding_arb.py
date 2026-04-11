"""
Funding Rate Strategy
======================
Philosophy: Funding rates on perpetual futures are a direct, recurring
transfer of capital between longs and shorts. When rates are extreme,
the market is heavily skewed. Two opportunities arise:

1. DELTA-NEUTRAL CARRY TRADE:
   Extreme positive funding (>15% annualized):
     - Short the perp, long spot = collect funding every 8h
     - Risk: basis can widen, liquidation on perp side
   Extreme negative funding:
     - Long the perp, short spot = collect funding every 8h

2. CONTRARIAN DIRECTIONAL SIGNAL:
   Extreme funding = crowded trades = setup for reversal
   When everyone is long (high positive funding), a long squeeze is brewing.
   Can be used to bias direction on other strategies.

This implementation focuses on using funding as a directional signal
to bias confidence scoring on momentum/breakout trades.
High-leverage funding arb requires spot + perp on same account —
this is mostly feasible on Hyperliquid (where you can do both).
"""
from __future__ import annotations

import logging
import time

from exchanges.base import BaseExchange, FundingRate
from strategies.base import BaseStrategy, Signal, SignalDirection

log = logging.getLogger("apex.strategy.funding_arb")

# Thresholds in annualized %
EXTREME_LONG_BIAS_THRESHOLD = 50.0    # >50% annual = crowded longs → short bias
EXTREME_SHORT_BIAS_THRESHOLD = -50.0  # <-50% annual = crowded shorts → long bias
CARRY_TRADE_THRESHOLD = 15.0          # >15% annual = carry trade viable


class FundingArbStrategy(BaseStrategy):
    name = "funding_arb"

    def __init__(self, config: dict):
        super().__init__(config)
        self.min_annual_rate: float = config.get("min_annual_rate_pct", 15.0)
        self.check_interval: int = config.get("check_interval_min", 30) * 60
        self._last_check: dict[str, float] = {}
        self._funding_cache: dict[str, FundingRate] = {}

    async def analyze(self, pair: str, venue: str, exchange: BaseExchange) -> Signal | None:
        now = time.time()
        cache_key = f"{venue}:{pair}"

        # Rate-limit checks
        if now - self._last_check.get(cache_key, 0) < self.check_interval:
            return None
        self._last_check[cache_key] = now

        try:
            funding = await exchange.get_funding_rate(pair)
        except Exception as e:
            log.debug("funding rate %s: %s", pair, e)
            return None

        if funding.rate == 0:
            return None

        self._funding_cache[cache_key] = funding
        annual = funding.annual_rate

        log.debug(
            "Funding %s/%s: %.4f%% (%.1f%% annual)",
            pair, venue, funding.rate * 100, annual
        )

        # ── Contrarian directional signal based on extreme funding ────
        current_price = await exchange.get_price(pair)
        if current_price == 0:
            return None

        if annual >= EXTREME_LONG_BIAS_THRESHOLD:
            # Market extremely long → fade longs → short signal
            # Crowded long + high funding = long squeeze setup
            stop = current_price * 1.02    # 2% stop above
            target = current_price * 0.94  # 6% target below
            confidence = min(annual / 200.0, 0.85)  # cap at 0.85

            log.info(
                "FUNDING SIGNAL: %s SHORT | annual=%.1f%% (crowd long squeeze setup)",
                pair, annual
            )
            return Signal(
                strategy=self.name,
                pair=pair,
                venue=venue,
                direction=SignalDirection.SHORT,
                confidence=confidence,
                entry_price=current_price,
                stop_price=stop,
                target_price=target,
                timeframe="8h",
                metadata={
                    "funding_rate": round(funding.rate * 100, 4),
                    "annual_rate": round(annual, 1),
                    "signal_type": "contrarian_short",
                    "reason": "extreme_positive_funding",
                },
            )

        if annual <= EXTREME_SHORT_BIAS_THRESHOLD:
            # Market extremely short → fade shorts → long signal
            stop = current_price * 0.98    # 2% stop below
            target = current_price * 1.06  # 6% target above
            confidence = min(abs(annual) / 200.0, 0.85)

            log.info(
                "FUNDING SIGNAL: %s LONG | annual=%.1f%% (crowd short squeeze setup)",
                pair, annual
            )
            return Signal(
                strategy=self.name,
                pair=pair,
                venue=venue,
                direction=SignalDirection.LONG,
                confidence=confidence,
                entry_price=current_price,
                stop_price=stop,
                target_price=target,
                timeframe="8h",
                metadata={
                    "funding_rate": round(funding.rate * 100, 4),
                    "annual_rate": round(annual, 1),
                    "signal_type": "contrarian_long",
                    "reason": "extreme_negative_funding",
                },
            )

        return None

    def get_funding_bias(self, pair: str, venue: str) -> float:
        """
        Returns a bias score for use by other strategies.
        Positive = funding favors longs (slightly bearish for contrarian).
        Negative = funding favors shorts (slightly bullish for contrarian).
        Range: -1.0 to +1.0
        """
        key = f"{venue}:{pair}"
        funding = self._funding_cache.get(key)
        if not funding:
            return 0.0
        return max(-1.0, min(1.0, funding.annual_rate / 100.0))
