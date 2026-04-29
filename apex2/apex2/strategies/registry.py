"""Strategy registry — name → class lookup."""
from __future__ import annotations

from .base import Strategy, StrategyContext
from .bond_equity_rotation import BondEquityRotation
from .defensive_momentum import DefensiveMomentum
from .donchian_trend import DonchianTrend
from .etf_momentum import ETFMomentum
from .pairs_trading import PairsTrading
from .rsi2_meanrev import RSI2MeanReversion

REGISTRY: dict[str, type[Strategy]] = {
    "etf_momentum": ETFMomentum,
    "rsi2_meanrev": RSI2MeanReversion,
    "donchian_trend": DonchianTrend,
    "pairs_trading": PairsTrading,
    "bond_equity_rotation": BondEquityRotation,
    "defensive_momentum": DefensiveMomentum,
}


def build(name: str, ctx: StrategyContext) -> Strategy:
    cls = REGISTRY.get(name)
    if cls is None:
        raise KeyError(f"unknown strategy: {name}. Known: {list(REGISTRY)}")
    return cls(ctx)


def universe_for(name: str, params: dict) -> list[str]:
    """Return the symbols a strategy needs so the data layer can preload them.

    Most strategies use `params['universe']`. Pairs trading uses `params['pairs']`
    (list of [a, b] lists). Bond/equity rotation uses ticker fields.
    """
    syms: set[str] = set()
    for s in params.get("universe", []) or []:
        syms.add(s)
    for pair in params.get("pairs", []) or []:
        for s in pair:
            syms.add(s)
    for key in ("benchmark", "equity_ticker", "bond_ticker"):
        v = params.get(key)
        if v:
            syms.add(v)
    return sorted(syms)
