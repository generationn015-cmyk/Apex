"""Crypto symbols used for free Binance Vision research scans."""
from __future__ import annotations

CORE_CRYPTO_UNIVERSE = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "ADAUSDT",
    "DOGEUSDT",
    "LINKUSDT",
    "AVAXUSDT",
    "LTCUSDT",
]


def default_crypto_symbols(limit: int | None = None) -> list[str]:
    if limit is None or limit <= 0:
        return list(CORE_CRYPTO_UNIVERSE)
    return CORE_CRYPTO_UNIVERSE[:limit]
