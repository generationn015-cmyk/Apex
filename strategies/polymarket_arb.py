"""
Polymarket YES/NO Complementary Arbitrage Strategy
=====================================================
Philosophy: On binary prediction markets, a YES share + NO share
redeems for exactly $1.00 at resolution. If you can buy BOTH for
less than $1.00 (minus fees), you've locked in risk-free profit.

Market efficiency leaves these gaps briefly — bots have narrowed
the average opportunity to ~2.7 seconds as of 2026. But they still
occur constantly across 500+ active markets, and even $0.005 profit
per pair compounds fast when cycling $250 repeatedly.

Strategy loop:
  1. Scan all active markets for YES_ask + NO_ask < $1.00 - fees
  2. Rank by profit per share
  3. Buy best opportunity (both sides simultaneously)
  4. Wait for market resolution OR sell when spread collapses

Risk:
  - Smart contract risk (Polygon / Conditional Token contracts)
  - Market resolves incorrectly (rare but has happened)
  - Gas fees on Polygon (small but real)
  - Opportunity may disappear before orders fill

Best conditions:
  - Geopolitics markets (0% fee = most profitable arb)
  - Sports markets (low 3% fee)
  - Avoid crypto markets (7.2% fee kills most arb)
  - Markets close to resolution date (less time risk)
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from exchanges.polymarket import PolymarketExchange
from strategies.base import BaseStrategy, Signal, SignalDirection

if TYPE_CHECKING:
    from exchanges.base import BaseExchange

log = logging.getLogger("apex.strategy.polymarket_arb")


class PolymarketArbStrategy(BaseStrategy):
    name = "polymarket_arb"

    def __init__(self, config: dict):
        super().__init__(config)
        # Override venues/pairs — Polymarket doesn't use pair lists
        self.venues = config.get("venues", ["polymarket"])
        self.pairs = []  # Not used — we scan all markets dynamically
        self.min_profit_pct: float = config.get("min_profit_pct", 0.5)
        self.max_bet_usd: float = config.get("max_bet_usd", 25.0)
        self.preferred_categories: list[str] = config.get(
            "preferred_categories",
            ["geopolitics", "sports", "economics"]
        )
        self._last_scan: float = 0
        self._scan_cooldown: int = config.get("scan_interval_sec", 15)

    async def analyze(self, pair: str, venue: str, exchange: "BaseExchange") -> Signal | None:
        """Not used for this strategy — uses analyze_all override instead."""
        return None

    async def analyze_all(self, exchanges: dict[str, "BaseExchange"]) -> list[Signal]:
        """
        Override to scan all Polymarket opportunities directly.
        Returns signals representing arb opportunities.
        """
        now = time.time()
        if now - self._last_scan < self._scan_cooldown:
            return []
        self._last_scan = now

        exchange = exchanges.get("polymarket")
        if not exchange or not isinstance(exchange, PolymarketExchange):
            return []

        try:
            opportunities = await exchange.find_yesno_arb()
        except Exception as e:
            log.debug("polymarket_arb scan: %s", e)
            return []

        signals = []
        for opp in opportunities:
            # Filter by category preference
            category = opp.get("category", "").lower()
            if self.preferred_categories and category not in self.preferred_categories:
                continue

            profit_pct = opp["profit_pct"]
            if profit_pct < self.min_profit_pct:
                continue

            # Use a synthetic "entry price" = total cost of both shares
            entry = opp["total_cost"]
            # Target = $1.00 (redemption value of YES+NO pair)
            # Stop = entry * 0.98 (in case we need to exit early at a loss)
            target = 1.0 - opp["estimated_fees"]
            stop = entry * 0.97

            # Confidence scales with profit margin and category
            confidence = self._calc_confidence(opp)

            # Encode arb info in metadata
            signal = Signal(
                strategy=self.name,
                pair=f"PM_ARB:{opp.get('condition_id', '')[:12]}",
                venue="polymarket",
                direction=SignalDirection.LONG,   # Always "long" — buying both sides
                confidence=confidence,
                entry_price=entry,
                stop_price=stop,
                target_price=target,
                timeframe="arb",
                metadata={
                    "yes_token_id": opp["yes_token_id"],
                    "no_token_id": opp["no_token_id"],
                    "yes_ask": opp["yes_ask"],
                    "no_ask": opp["no_ask"],
                    "profit_pct": profit_pct,
                    "category": category,
                    "question": opp.get("question", "")[:80],
                    "arb_type": "yesno_complementary",
                    "max_bet_usd": self.max_bet_usd,
                },
            )
            signals.append(signal)
            log.info(
                "PM ARB: %.2f%% profit | %s | %s",
                profit_pct,
                category.upper(),
                opp.get("question", "")[:60],
            )

        return signals[:3]   # Return top 3 max to avoid flooding

    def _calc_confidence(self, opp: dict) -> float:
        """Score the arb opportunity."""
        score = 0.0

        # Profit margin (0-0.5): 0.5% = 0.0, 3%+ = 0.5
        profit_score = min(opp["profit_pct"] / 6.0, 0.5)
        score += profit_score

        # Category preference (0-0.3): lower fees = better
        fee_rate = opp.get("fee_rate", 0.05)
        fee_score = max(0, (0.072 - fee_rate) / 0.072) * 0.3
        score += fee_score

        # Volume liquidity (0-0.2): higher volume = easier to fill
        vol = float(opp.get("volume_24h", 0))
        vol_score = min(vol / 100_000, 1.0) * 0.2
        score += vol_score

        return round(min(score, 1.0), 3)
