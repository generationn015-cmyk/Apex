"""VIX regime filter — protection guard that disables risk-on strategies in high-fear regimes.

VIX > 25 → market is in stress mode; mean-reversion and trend strategies degrade.
This guard blocks NEW entries when VIX (^VIX) is above threshold.

Caches the latest close price for ~1 hour so we don't hammer yfinance every poll.
"""
from __future__ import annotations

import logging
import time
from datetime import date, timedelta

import pandas as pd

from .protections import Protection, ProtectionContext

log = logging.getLogger("apex2.risk.vix")


class VIXRegimeFilter(Protection):
    name = "vix_regime"

    def __init__(self, threshold: float = 25.0, cache_ttl_seconds: int = 3600):
        self.threshold = float(threshold)
        self.cache_ttl = cache_ttl_seconds
        self._cached_value: float | None = None
        self._cached_at: float = 0.0

    def _read_vix(self) -> float | None:
        now = time.time()
        if self._cached_value is not None and (now - self._cached_at) < self.cache_ttl:
            return self._cached_value
        try:
            import yfinance as yf
            df = yf.download(
                "^VIX",
                start=(date.today() - timedelta(days=5)),
                end=date.today() + timedelta(days=1),
                interval="1d",
                progress=False,
                auto_adjust=False,
            )
            if df.empty:
                return self._cached_value
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            v = float(df["Close"].iloc[-1])
            self._cached_value = v
            self._cached_at = now
            return v
        except Exception as e:
            log.warning("VIX fetch failed: %s", e)
            return self._cached_value

    def check(self, ctx: ProtectionContext) -> tuple[bool, str]:
        vix = self._read_vix()
        if vix is None:
            return True, "vix_unavailable"
        if vix >= self.threshold:
            return False, f"VIX={vix:.1f} >= {self.threshold:.1f} (stress regime)"
        return True, f"VIX={vix:.1f} ok"
