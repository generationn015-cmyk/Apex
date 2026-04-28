"""Indicator correctness tests."""
from __future__ import annotations

import numpy as np
import pandas as pd

from apex2.indicators.features import atr, donchian, momentum, rsi, sma


def test_sma_constant_series():
    s = pd.Series([10.0] * 30)
    assert sma(s, 5).iloc[-1] == 10.0


def test_rsi_monotone_up_is_high():
    s = pd.Series(np.arange(1, 100, dtype=float))
    assert rsi(s, 14).iloc[-1] > 90


def test_atr_positive_on_realistic_bars():
    n = 50
    close = pd.Series(np.linspace(100, 110, n))
    high = close + 1
    low = close - 1
    a = atr(high, low, close, 14).iloc[-1]
    assert a > 0


def test_donchian_window_high_is_max():
    high = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=float)
    low = pd.Series([0, 1, 2, 3, 4, 5, 6, 7, 8, 9], dtype=float)
    upper, lower = donchian(high, low, 5)
    assert upper.iloc[-1] == 10
    assert lower.iloc[-1] == 5


def test_momentum_skip_window():
    close = pd.Series(np.linspace(100, 200, 100))
    m = momentum(close, lookback=20, skip=5).iloc[-1]
    assert m > 0
