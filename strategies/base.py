"""
Abstract base class for all trading strategies.
Each strategy receives candle data and returns a Signal (or None).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from exchanges.base import BaseExchange, Candle


class SignalDirection(str, Enum):
    LONG = "long"
    SHORT = "short"
    CLOSE_LONG = "close_long"
    CLOSE_SHORT = "close_short"


@dataclass
class Signal:
    """A trading signal produced by a strategy."""
    strategy: str
    pair: str
    venue: str
    direction: SignalDirection
    confidence: float           # 0.0 → 1.0
    entry_price: float
    stop_price: float
    target_price: float
    timeframe: str = ""
    metadata: dict = field(default_factory=dict)

    @property
    def risk_reward(self) -> float:
        """Calculate R:R ratio."""
        risk = abs(self.entry_price - self.stop_price)
        reward = abs(self.target_price - self.entry_price)
        return reward / risk if risk > 0 else 0.0

    @property
    def stop_pct(self) -> float:
        """Stop loss distance as % of entry."""
        return abs(self.entry_price - self.stop_price) / self.entry_price * 100

    @property
    def target_pct(self) -> float:
        """Target distance as % of entry."""
        return abs(self.target_price - self.entry_price) / self.entry_price * 100

    def __repr__(self) -> str:
        return (
            f"Signal({self.strategy} | {self.pair} | {self.direction.value.upper()} | "
            f"entry={self.entry_price:.2f} stop={self.stop_price:.2f} "
            f"target={self.target_price:.2f} RR={self.risk_reward:.1f}x "
            f"conf={self.confidence:.0%})"
        )


class BaseStrategy(ABC):
    """Abstract trading strategy."""

    name: str = "base"

    def __init__(self, config: dict):
        self.config = config
        self.enabled: bool = config.get("enabled", True)
        self.priority: int = config.get("priority", 5)
        self.venues: list[str] = config.get("venues", [])
        self.pairs: list[str] = config.get("pairs", [])

    @abstractmethod
    async def analyze(
        self,
        pair: str,
        venue: str,
        exchange: "BaseExchange",
    ) -> Signal | None:
        """
        Analyze the market and return a Signal if conditions are met,
        or None if no edge is found.
        """

    async def analyze_all(
        self, exchanges: dict[str, "BaseExchange"]
    ) -> list[Signal]:
        """Run analysis across all configured pairs and venues."""
        signals = []
        for venue in self.venues:
            if venue not in exchanges:
                continue
            exchange = exchanges[venue]
            for pair in self.pairs:
                try:
                    signal = await self.analyze(pair, venue, exchange)
                    if signal:
                        signals.append(signal)
                except Exception as e:
                    import logging
                    logging.getLogger(f"apex.strategy.{self.name}").error(
                        "analyze %s/%s: %s", pair, venue, e
                    )
        return signals
