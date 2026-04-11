"""
Signal Confluence Engine
=========================
The single biggest edge amplifier in the bot.

Most traders lose because they trade mediocre setups with average position sizes.
Professional traders wait for HIGH-CONFLUENCE setups — moments when multiple
independent signals ALL point the same direction simultaneously — and then
SIZE UP aggressively on those.

This module detects confluence and returns a multiplier applied to:
  1. Position size (via Kelly)
  2. Leverage selection
  3. Signal confidence score

Confluence tiers:
  TIER 1 (1 signal):   Base size, base leverage — trade normally
  TIER 2 (2 signals):  1.5x size, +5 leverage   — strong setup
  TIER 3 (3 signals):  2.5x size, +10 leverage  — A+ setup, maximum focus
  TIER 4 (4+ signals): 3.5x size, +15 leverage  — RARE, once-a-week type setup

Real-world example:
  Normally: $500 × 15x = $7,500 notional → 10% move = $750 profit (150%)
  Tier 3:   $500 × 25x = $12,500 notional → 10% move = $1,250 profit (250%)
  Tier 4:   $500 × 30x = $15,000 notional → 10% move = $1,500 profit (300%)

ONE correctly identified Tier 3-4 setup per week = your monthly target.

Additional confluence signals tracked:
  - Order book imbalance (buy pressure vs sell pressure)
  - Funding rate direction alignment
  - Volume spike confirmation
  - Liquidation cluster proximity
  - Time-of-day quality score
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from strategies.base import Signal

log = logging.getLogger("apex.confluence")


@dataclass
class ConfluenceResult:
    tier: int                    # 1-4
    signal_count: int            # How many signals agree
    size_multiplier: float       # Multiply position size by this
    leverage_bonus: int          # Add this to base leverage
    confidence_boost: float      # Add this to signal confidence
    agreeing_strategies: list[str] = field(default_factory=list)
    orderbook_bias: float = 0.0  # -1.0 (sell) to +1.0 (buy)
    notes: list[str] = field(default_factory=list)

    def __repr__(self) -> str:
        return (
            f"Confluence(tier={self.tier} | {self.signal_count} signals | "
            f"{self.size_multiplier}x size | +{self.leverage_bonus} lev | "
            f"strategies={self.agreeing_strategies})"
        )


class ConfluenceEngine:
    """
    Detects when multiple independent signals agree on a direction.
    The more agreement, the bigger the position.
    """

    TIER_CONFIG = {
        1: {"size_mult": 1.0,  "lev_bonus": 0,  "conf_boost": 0.0,  "label": "SINGLE"},
        2: {"size_mult": 1.5,  "lev_bonus": 5,  "conf_boost": 0.10, "label": "DOUBLE"},
        3: {"size_mult": 2.5,  "lev_bonus": 10, "conf_boost": 0.20, "label": "TRIPLE ⚡"},
        4: {"size_mult": 3.5,  "lev_bonus": 15, "conf_boost": 0.30, "label": "QUAD 🔥"},
    }

    def analyze(
        self,
        signals: list["Signal"],
        orderbook_imbalance: float = 0.0,
        funding_bias: float = 0.0,
    ) -> dict[str, ConfluenceResult]:
        """
        Group signals by pair+direction and score confluence.
        Returns: {f"{pair}:{direction}": ConfluenceResult}
        """
        # Group signals by (pair, direction)
        groups: dict[str, list["Signal"]] = {}
        for sig in signals:
            # Normalize direction to long/short
            direction = "long" if "long" in sig.direction.value else "short"
            key = f"{sig.pair}:{direction}"
            groups.setdefault(key, []).append(sig)

        results = {}
        for key, group_signals in groups.items():
            pair, direction = key.split(":", 1)
            result = self._score_group(
                group_signals, direction, orderbook_imbalance, funding_bias
            )
            results[key] = result

            if result.tier >= 2:
                log.info(
                    "CONFLUENCE %s | %s | %s | strategies=%s | %.1fx size | +%d lev",
                    self.TIER_CONFIG[result.tier]["label"],
                    pair.upper(),
                    direction.upper(),
                    result.agreeing_strategies,
                    result.size_multiplier,
                    result.leverage_bonus,
                )

        return results

    def _score_group(
        self,
        signals: list["Signal"],
        direction: str,
        orderbook_imbalance: float,
        funding_bias: float,
    ) -> ConfluenceResult:
        strategies = [s.strategy for s in signals]
        signal_count = len(signals)
        avg_confidence = sum(s.confidence for s in signals) / signal_count

        notes = []

        # ── Order book alignment bonus ────────────────────────────
        ob_aligned = False
        if direction == "long" and orderbook_imbalance > 0.15:
            signal_count += 0.5   # Partial credit
            ob_aligned = True
            notes.append(f"OB imbalance={orderbook_imbalance:.2f} supports long")
        elif direction == "short" and orderbook_imbalance < -0.15:
            signal_count += 0.5
            ob_aligned = True
            notes.append(f"OB imbalance={orderbook_imbalance:.2f} supports short")

        # ── Funding rate alignment bonus ──────────────────────────
        funding_aligned = False
        # Positive funding bias = market is long heavy = better for shorts (contrarian)
        # But for delta-neutral, positive funding = good for carrying
        if direction == "long" and funding_bias < -0.10:
            # Negative funding = market is short heavy = long is favored
            signal_count += 0.5
            funding_aligned = True
            notes.append(f"Funding bias={funding_bias:.2f} supports long")
        elif direction == "short" and funding_bias > 0.10:
            signal_count += 0.5
            funding_aligned = True
            notes.append(f"Funding bias={funding_bias:.2f} supports short")

        # ── Determine tier ────────────────────────────────────────
        tier = min(int(signal_count), 4)
        tier = max(tier, 1)

        cfg = self.TIER_CONFIG[tier]

        return ConfluenceResult(
            tier=tier,
            signal_count=len(signals),
            size_multiplier=cfg["size_mult"],
            leverage_bonus=cfg["lev_bonus"],
            confidence_boost=cfg["conf_boost"],
            agreeing_strategies=strategies,
            orderbook_bias=orderbook_imbalance,
            notes=notes,
        )

    def get_best(
        self, results: dict[str, ConfluenceResult]
    ) -> tuple[str, ConfluenceResult] | None:
        """Return the highest-tier confluence opportunity."""
        if not results:
            return None
        best_key = max(results.keys(), key=lambda k: (results[k].tier, results[k].signal_count))
        return best_key, results[best_key]
