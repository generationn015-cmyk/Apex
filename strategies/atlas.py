"""
ATLAS — SMA Trend Agent  (BTC/USDT, ETH/USDT)

What was wrong before:
  - SMA 10/50 on 5-min = 200+ whipsaws per day
  - No trend quality filter → traded sideways chop equally
  - Fixed 5% stop → too wide sometimes, too tight others

Fixes:
  - Operate on 1h candles (less noise, more signal)
  - ADX > 25 gate: only trade when market is actually trending
  - Volume confirmation: candle must close on above-average volume
  - ATR-based dynamic stop loss (1.5× ATR14)
  - Higher-timeframe (4h) trend filter: long only above 4h SMA50, short below
  - Minimum 0.5% gap between SMA10 and SMA50 to avoid noise band
"""
import pandas_ta as ta
import pandas as pd


def analyze_ATLAS(df: pd.DataFrame, df_4h: pd.DataFrame | None = None) -> dict | None:
    """
    Args:
        df:    1h OHLCV DataFrame (need ≥ 60 candles)
        df_4h: 4h OHLCV DataFrame for HTF filter (optional but recommended)

    Returns dict with keys: signal, strength, stop_loss_pct, indicators
    """
    if df is None or len(df) < 60:
        return None

    c = df["close"]
    h = df["high"]
    lo = df["low"]

    # ── Indicators ──────────────────────────────────────────────────────────
    df = df.copy()
    df["sma10"]  = ta.sma(c, 10)
    df["sma50"]  = ta.sma(c, 50)
    df["adx"]    = ta.adx(h, lo, c, 14)["ADX_14"]
    df["atr"]    = ta.atr(h, lo, c, 14)
    df["vol_ma"] = ta.sma(df["volume"], 20)

    row  = df.iloc[-1]
    prev = df.iloc[-2]

    sma10  = float(row["sma10"])
    sma50  = float(row["sma50"])
    adx    = float(row["adx"])
    atr    = float(row["atr"])
    close  = float(row["close"])
    volume = float(row["volume"])
    vol_ma = float(row["vol_ma"])

    # ── Gate 1: ADX trend quality ────────────────────────────────────────────
    if adx < 25:
        return {"signal": "NONE", "strength": 0.0,
                "indicators": {"adx": round(adx, 1), "reason": "no_trend"}}

    # ── Gate 2: Volume confirmation ──────────────────────────────────────────
    vol_ratio = volume / vol_ma if vol_ma > 0 else 0
    if vol_ratio < 0.8:
        return {"signal": "NONE", "strength": 0.0,
                "indicators": {"vol_ratio": round(vol_ratio, 2), "reason": "low_volume"}}

    # ── Gate 3: SMA gap must be meaningful (≥ 0.5%) ──────────────────────────
    gap_pct = abs(sma10 - sma50) / sma50 * 100
    if gap_pct < 0.5:
        return {"signal": "NONE", "strength": 0.0,
                "indicators": {"gap_pct": round(gap_pct, 3), "reason": "sma_noise_band"}}

    # ── HTF filter (4h trend direction) ─────────────────────────────────────
    htf_bull = True   # Default permissive if no 4h data
    htf_bear = True
    if df_4h is not None and len(df_4h) >= 50:
        df_4h = df_4h.copy()
        df_4h["sma50_4h"] = ta.sma(df_4h["close"], 50)
        last_4h = df_4h.iloc[-1]
        htf_bull = float(last_4h["close"]) > float(last_4h["sma50_4h"])
        htf_bear = float(last_4h["close"]) < float(last_4h["sma50_4h"])

    # ── Signal logic ─────────────────────────────────────────────────────────
    bull = sma10 > sma50 and close > sma10
    bear = sma10 < sma50 and close < sma10

    prev_bull = float(prev["sma10"]) > float(prev["sma50"])
    fresh_cross_up = bull and not prev_bull
    fresh_cross_dn = bear and prev_bull

    signal   = "NONE"
    strength = 0.0

    if bull and htf_bull:
        signal   = "BUY"
        strength = 0.55          # continuation — below 0.65 threshold
        if fresh_cross_up:
            strength = 0.85      # fresh cross — tradeable event
        if adx > 35:
            strength += 0.10     # Strong trend bonus
        if vol_ratio > 1.5:
            strength += 0.05     # High volume bonus

    elif bear and htf_bear:
        signal   = "SELL"
        strength = 0.55          # continuation — below 0.65 threshold
        if fresh_cross_dn:
            strength = 0.85      # fresh cross — tradeable event
        if adx > 35:
            strength += 0.10
        if vol_ratio > 1.5:
            strength += 0.05

    strength = min(round(strength, 2), 1.0)

    # ── ATR-based dynamic stop loss ──────────────────────────────────────────
    atr_stop_pct = (atr * 1.5 / close) * 100   # expressed as % for risk manager

    return {
        "signal":        signal,
        "strength":      strength,
        "stop_loss_pct": round(atr_stop_pct, 3),
        "indicators": {
            "sma10":      round(sma10, 4),
            "sma50":      round(sma50, 4),
            "adx":        round(adx, 1),
            "atr":        round(atr, 4),
            "vol_ratio":  round(vol_ratio, 2),
            "gap_pct":    round(gap_pct, 3),
            "fresh_cross": fresh_cross_up or fresh_cross_dn,
            "htf_aligned": (signal == "BUY" and htf_bull) or (signal == "SELL" and htf_bear),
        },
    }
