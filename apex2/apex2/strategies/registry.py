"""Strategy registry — name → class lookup."""
from __future__ import annotations

from .base import Strategy, StrategyContext
from .donchian_trend import DonchianTrend
from .etf_momentum import ETFMomentum
from .rsi2_meanrev import RSI2MeanReversion

REGISTRY: dict[str, type[Strategy]] = {
    "etf_momentum": ETFMomentum,
    "rsi2_meanrev": RSI2MeanReversion,
    "donchian_trend": DonchianTrend,
}


def build(name: str, ctx: StrategyContext) -> Strategy:
    cls = REGISTRY.get(name)
    if cls is None:
        raise KeyError(f"unknown strategy: {name}. Known: {list(REGISTRY)}")
    return cls(ctx)


def universe_for(name: str, params: dict) -> list[str]:
    """Return universe tickers a given strategy will need so the data layer can preload."""
    return list(params.get("universe", []))
