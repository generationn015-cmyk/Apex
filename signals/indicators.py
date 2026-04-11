"""
Pure technical analysis indicators.
All functions take a list/array of prices and return values.
No side effects, no exchange calls — pure math.
"""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np
import pandas as pd


# ── Moving Averages ───────────────────────────────────────────────────────────

def ema(prices: Sequence[float], period: int) -> np.ndarray:
    """Exponential Moving Average."""
    s = pd.Series(prices, dtype=float)
    return s.ewm(span=period, adjust=False).mean().values


def sma(prices: Sequence[float], period: int) -> np.ndarray:
    """Simple Moving Average."""
    s = pd.Series(prices, dtype=float)
    return s.rolling(period).mean().values


# ── Momentum Indicators ───────────────────────────────────────────────────────

def rsi(prices: Sequence[float], period: int = 14) -> np.ndarray:
    """
    Relative Strength Index.
    Returns array of RSI values (0-100). NaN for first `period` bars.
    """
    s = pd.Series(prices, dtype=float)
    delta = s.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return (100 - (100 / (1 + rs))).values


def macd(
    prices: Sequence[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    MACD indicator.
    Returns (macd_line, signal_line, histogram).
    """
    fast_ema = ema(prices, fast)
    slow_ema = ema(prices, slow)
    macd_line = fast_ema - slow_ema
    signal_line = ema(macd_line.tolist(), signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def adx(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> np.ndarray:
    """
    Average Directional Index.
    Returns ADX values (0-100). Higher = stronger trend.
    """
    h = np.array(highs, dtype=float)
    l = np.array(lows, dtype=float)
    c = np.array(closes, dtype=float)
    n = len(c)

    tr = np.maximum(h[1:] - l[1:], np.abs(h[1:] - c[:-1]))
    tr = np.maximum(tr, np.abs(l[1:] - c[:-1]))

    plus_dm = h[1:] - h[:-1]
    minus_dm = l[:-1] - l[1:]
    plus_dm = np.where((plus_dm > minus_dm) & (plus_dm > 0), plus_dm, 0.0)
    minus_dm = np.where((minus_dm > plus_dm) & (minus_dm > 0), minus_dm, 0.0)

    def smooth(arr: np.ndarray, p: int) -> np.ndarray:
        result = np.full(len(arr), np.nan)
        if len(arr) < p:
            return result
        result[p - 1] = arr[:p].sum()
        for i in range(p, len(arr)):
            result[i] = result[i - 1] - result[i - 1] / p + arr[i]
        return result

    str_ = smooth(tr, period)
    sdm_plus = smooth(plus_dm, period)
    sdm_minus = smooth(minus_dm, period)

    di_plus = 100 * sdm_plus / np.where(str_ == 0, np.nan, str_)
    di_minus = 100 * sdm_minus / np.where(str_ == 0, np.nan, str_)
    dx = 100 * np.abs(di_plus - di_minus) / np.where((di_plus + di_minus) == 0, np.nan, di_plus + di_minus)

    adx_vals = smooth(dx, period)
    padded = np.full(n, np.nan)
    padded[1:] = adx_vals
    return padded


# ── Volatility Indicators ─────────────────────────────────────────────────────

def atr(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> np.ndarray:
    """Average True Range."""
    h = np.array(highs, dtype=float)
    l = np.array(lows, dtype=float)
    c = np.array(closes, dtype=float)
    tr = np.maximum(h[1:] - l[1:], np.abs(h[1:] - c[:-1]))
    tr = np.maximum(tr, np.abs(l[1:] - c[:-1]))
    atr_series = pd.Series(tr).ewm(com=period - 1, adjust=False).mean().values
    padded = np.full(len(c), np.nan)
    padded[1:] = atr_series
    return padded


def bollinger_bands(
    prices: Sequence[float],
    period: int = 20,
    std_dev: float = 2.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Bollinger Bands.
    Returns (upper_band, middle_band, lower_band).
    """
    s = pd.Series(prices, dtype=float)
    mid = s.rolling(period).mean()
    std = s.rolling(period).std(ddof=0)
    upper = mid + std_dev * std
    lower = mid - std_dev * std
    return upper.values, mid.values, lower.values


def bb_width(upper: np.ndarray, lower: np.ndarray, mid: np.ndarray) -> np.ndarray:
    """Bollinger Band Width as % of mid. Low = squeeze."""
    return np.where(mid == 0, np.nan, (upper - lower) / mid * 100)


def bb_percent_b(prices: Sequence[float], upper: np.ndarray, lower: np.ndarray) -> np.ndarray:
    """BB %B: 0=at lower band, 1=at upper band, >1 or <0 = breakout."""
    p = np.array(prices, dtype=float)
    bandwidth = upper - lower
    return np.where(bandwidth == 0, 0.5, (p - lower) / bandwidth)


# ── Volume Indicators ─────────────────────────────────────────────────────────

def volume_sma(volumes: Sequence[float], period: int = 20) -> np.ndarray:
    return sma(volumes, period)


def vwap(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    volumes: Sequence[float],
) -> np.ndarray:
    """Volume Weighted Average Price."""
    typical = (np.array(highs) + np.array(lows) + np.array(closes)) / 3
    cumvol = np.cumsum(np.array(volumes))
    cumtpv = np.cumsum(typical * np.array(volumes))
    return np.where(cumvol == 0, typical, cumtpv / cumvol)


# ── Signal Detection ──────────────────────────────────────────────────────────

def ema_crossover(fast: np.ndarray, slow: np.ndarray) -> tuple[bool, bool]:
    """
    Detect EMA crossover on the last two bars.
    Returns (bullish_cross, bearish_cross).
    Bullish: fast crosses above slow on the last bar.
    Bearish: fast crosses below slow on the last bar.
    """
    if len(fast) < 2 or len(slow) < 2:
        return False, False
    prev_diff = fast[-2] - slow[-2]
    curr_diff = fast[-1] - slow[-1]
    bullish = prev_diff < 0 and curr_diff >= 0
    bearish = prev_diff > 0 and curr_diff <= 0
    return bullish, bearish


def detect_squeeze(width: np.ndarray, lookback: int = 20) -> bool:
    """
    True if current BB width is at a N-bar low (squeeze condition).
    """
    if len(width) < lookback:
        return False
    recent = width[-lookback:]
    valid = recent[~np.isnan(recent)]
    if len(valid) < 2:
        return False
    return float(valid[-1]) == float(valid.min())


def is_breakout(
    prices: Sequence[float],
    upper: np.ndarray,
    lower: np.ndarray,
    volumes: Sequence[float],
    vol_avg: np.ndarray,
    volume_mult: float = 2.0,
) -> tuple[bool, bool]:
    """
    Detect BB breakout with volume confirmation.
    Returns (bullish_breakout, bearish_breakout).
    """
    if len(prices) < 2:
        return False, False
    close = prices[-1]
    vol = volumes[-1]
    avg_vol = vol_avg[-1]
    volume_confirmed = not np.isnan(avg_vol) and vol >= avg_vol * volume_mult
    bullish = close > upper[-1] and not np.isnan(upper[-1]) and volume_confirmed
    bearish = close < lower[-1] and not np.isnan(lower[-1]) and volume_confirmed
    return bullish, bearish


# ── Utility ───────────────────────────────────────────────────────────────────

def last(arr: np.ndarray) -> float:
    """Get the last non-NaN value from an array."""
    valid = arr[~np.isnan(arr)]
    return float(valid[-1]) if len(valid) > 0 else float("nan")


def crosses_above(a: np.ndarray, b: np.ndarray | float) -> bool:
    """True if `a` crossed above `b` on the last bar."""
    b_val = b if isinstance(b, (int, float)) else b[-1]
    b_prev = b if isinstance(b, (int, float)) else b[-2]
    return float(a[-2]) < float(b_prev) and float(a[-1]) >= float(b_val)


def crosses_below(a: np.ndarray, b: np.ndarray | float) -> bool:
    """True if `a` crossed below `b` on the last bar."""
    b_val = b if isinstance(b, (int, float)) else b[-1]
    b_prev = b if isinstance(b, (int, float)) else b[-2]
    return float(a[-2]) > float(b_prev) and float(a[-1]) <= float(b_val)
