"""
Liquidation Cascade Hunter
============================
Philosophy: Large clusters of leveraged positions sitting just above or
below the current price are fuel. When price taps into these clusters,
the cascade of forced liquidations accelerates the move dramatically.
This strategy hunts for those setups and positions ahead of the trigger.

Data source: Coinglass liquidation heatmap API (free tier available).
Signal logic:
  1. Fetch liquidation cluster map for BTC/ETH
  2. Identify the largest clusters within proximity_pct of current price
  3. If a massive cluster sits above price → long setup (liquidations will
     push price UP through them as longs get liquidated driving price up,
     wait — actually long liquidations push price DOWN, short liquidations
     push price UP)

  Corrected logic:
  - Large cluster of LONG liquidations ABOVE price → if price rises into
    them, forced sells create selling pressure → DON'T expect easy up move
  - Large cluster of SHORT liquidations ABOVE price → if price rises into
    them, forced buys of shorts create buying pressure → LONG setup
  - Large cluster of LONG liquidations BELOW price → if price drops into
    them, forced sells accelerate downward → SHORT setup

In practice: look for the nearest large cluster and trade toward it,
as price is attracted to liquidity like a magnet.
"""
from __future__ import annotations

import logging
import time

import aiohttp

from exchanges.base import BaseExchange
from strategies.base import BaseStrategy, Signal, SignalDirection

log = logging.getLogger("apex.strategy.liquidation_cascade")

COINGLASS_URL = "https://open-api.coinglass.com/public/v2/liquidation_map"


class LiquidationCascadeStrategy(BaseStrategy):
    name = "liquidation_cascade"

    def __init__(self, config: dict):
        super().__init__(config)
        self.min_cluster_usd: float = config.get("min_cluster_size_usd", 5_000_000)
        self.proximity_pct: float = config.get("proximity_pct", 0.5)
        self.stop_pct: float = config.get("stop_pct", 0.8)
        self.target_pct: float = config.get("target_pct", 2.0)
        self._cluster_cache: dict = {}
        self._cache_ts: float = 0
        self._cache_ttl: int = 300   # 5 minutes

    async def analyze(self, pair: str, venue: str, exchange: BaseExchange) -> Signal | None:
        try:
            current_price = await exchange.get_price(pair)
        except Exception as e:
            log.debug("get_price %s: %s", pair, e)
            return None

        if current_price == 0:
            return None

        clusters = await self._fetch_clusters(pair)
        if not clusters:
            return None

        proximity_threshold = current_price * self.proximity_pct / 100

        best_long_cluster = None
        best_short_cluster = None

        for cluster in clusters:
            cluster_price = cluster["price"]
            cluster_size = cluster["size_usd"]

            if cluster_size < self.min_cluster_usd:
                continue

            distance = abs(cluster_price - current_price)
            if distance > proximity_threshold:
                continue

            # Cluster is above current price → short liquidations above → long signal
            if cluster_price > current_price:
                if best_long_cluster is None or cluster_size > best_long_cluster["size_usd"]:
                    best_long_cluster = cluster

            # Cluster is below current price → long liquidations below → short signal
            if cluster_price < current_price:
                if best_short_cluster is None or cluster_size > best_short_cluster["size_usd"]:
                    best_short_cluster = cluster

        # Prefer the larger cluster
        if best_long_cluster and best_short_cluster:
            if best_long_cluster["size_usd"] >= best_short_cluster["size_usd"]:
                best_short_cluster = None
            else:
                best_long_cluster = None

        if best_long_cluster:
            stop = current_price * (1 - self.stop_pct / 100)
            target = best_long_cluster["price"] * 1.002  # just past the cluster
            confidence = self._calc_confidence(best_long_cluster["size_usd"], current_price, best_long_cluster["price"])
            log.info(
                "LIQ SIGNAL: %s LONG | cluster=$%.0fM @ %.2f (proximity=%.2f%%)",
                pair, best_long_cluster["size_usd"] / 1e6, best_long_cluster["price"],
                abs(best_long_cluster["price"] - current_price) / current_price * 100,
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
                timeframe="5m",
                metadata={
                    "cluster_price": best_long_cluster["price"],
                    "cluster_size_usd": best_long_cluster["size_usd"],
                    "type": "short_liq_above",
                },
            )

        if best_short_cluster:
            stop = current_price * (1 + self.stop_pct / 100)
            target = best_short_cluster["price"] * 0.998
            confidence = self._calc_confidence(best_short_cluster["size_usd"], current_price, best_short_cluster["price"])
            log.info(
                "LIQ SIGNAL: %s SHORT | cluster=$%.0fM @ %.2f",
                pair, best_short_cluster["size_usd"] / 1e6, best_short_cluster["price"],
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
                timeframe="5m",
                metadata={
                    "cluster_price": best_short_cluster["price"],
                    "cluster_size_usd": best_short_cluster["size_usd"],
                    "type": "long_liq_below",
                },
            )

        return None

    async def _fetch_clusters(self, pair: str) -> list[dict]:
        """
        Fetch liquidation heatmap data from Coinglass.
        Falls back to empty list if API unavailable.
        """
        now = time.time()
        cache_key = pair

        if cache_key in self._cluster_cache and (now - self._cache_ts) < self._cache_ttl:
            return self._cluster_cache[cache_key]

        # Normalize pair for Coinglass
        symbol = pair.replace("USDT", "").replace("USDC", "")

        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=5)
            ) as session:
                async with session.get(
                    COINGLASS_URL,
                    params={"symbol": symbol, "interval": "12h"},
                    headers={"accept": "application/json"},
                ) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
                    clusters = self._parse_coinglass(data)
                    self._cluster_cache[cache_key] = clusters
                    self._cache_ts = now
                    return clusters
        except Exception as e:
            log.debug("coinglass fetch %s: %s", symbol, e)
            return []

    def _parse_coinglass(self, data: dict) -> list[dict]:
        """Parse Coinglass liquidation map response into cluster list."""
        clusters = []
        try:
            liq_map = data.get("data", {}).get("liqMap", {})
            for price_str, size_info in liq_map.items():
                price = float(price_str)
                size_usd = float(size_info.get("l", 0)) + float(size_info.get("s", 0))
                if size_usd > 0:
                    clusters.append({"price": price, "size_usd": size_usd})
        except Exception as e:
            log.debug("parse coinglass: %s", e)
        clusters.sort(key=lambda x: x["size_usd"], reverse=True)
        return clusters

    def _calc_confidence(self, cluster_size: float, current_price: float, cluster_price: float) -> float:
        """Higher cluster size + closer proximity = higher confidence."""
        size_score = min(cluster_size / 50_000_000, 1.0)   # $50M = max score
        proximity_pct = abs(cluster_price - current_price) / current_price * 100
        prox_score = max(0, 1.0 - proximity_pct / self.proximity_pct)
        return round((size_score * 0.6 + prox_score * 0.4), 3)
