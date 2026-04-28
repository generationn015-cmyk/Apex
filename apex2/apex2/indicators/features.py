"""Indicator helpers. Hand-rolled to avoid pandas-ta dependency at import time."""
from __future__ import annotations

import numpy as np
import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    delta = s.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    avg_loss = loss.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = avg_gain / avg_loss
    out = 100 - (100 / (1 + rs))
    # If avg_loss is 0 we get inf/NaN — by convention RSI = 100.
    out = out.where(avg_loss != 0, 100.0)
    return out


def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low).abs(), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def donchian(high: pd.Series, low: pd.Series, n: int) -> tuple[pd.Series, pd.Series]:
    upper = high.rolling(n, min_periods=n).max()
    lower = low.rolling(n, min_periods=n).min()
    return upper, lower


def momentum(close: pd.Series, lookback: int, skip: int = 0) -> pd.Series:
    """Total return over lookback, skipping the most recent `skip` bars (to mute reversal)."""
    end = close.shift(skip)
    start = close.shift(skip + lookback)
    return (end / start) - 1
