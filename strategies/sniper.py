"""
SNIPER — Hybrid Regime Agent  (BTC/USDT, SOL/USDT)

What was wrong before:
  - Pure mean-reversion (RSI 30/70) never fires in trending crypto markets
  - RSI hits 30 most often DURING a crash → caught falling knives
  - No regime detection → same logic in all market conditions

Fixes — Regime-switching approach:
  TRENDING regime (ADX > 28):
    → Bollinger Band BREAKOUT mode
    → BUY when price closes ABOVE upper band with volume surge
    → SELL when price closes BELOW lower band with volume surge
    → ATR trailing stop
    → This captures the momentum moves that killed pure mean-reversion

  RANGING regime (ADX < 22):
    → RSI mean-reversion mode (improved thresholds 35/65)
    → Require price to be in bottom/top 20% of BB range
    → Additional stochastic confirmation (avoid chop)
    → Fixed 2x ATR stop (tighter in ranging markets)

  Ambiguous regime (22 ≤ ADX ≤ 28): → NONE (wait for clarity)
"""
import pandas_ta as ta
import pandas as pd


def analyze_SNIPER(df: pd.DataFrame, df_4h: pd.DataFrame | None = None) -> dict | None:
    if df is None or len(df) < 50:
        return None

    c  = df["close"]
    h  = df["high"]
    lo = df["low"]

    df = df.copy()
    df["atr"]    = ta.atr(h, lo, c, 14)
    df["adx"]    = ta.adx(h, lo, c, 14)["ADX_14"]
    df["rsi"]    = ta.rsi(c, 14)
    df["vol_ma"] = ta.sma(df["volume"], 20)

    bb = ta.bbands(c, 20, 2.0)
    df["bbu"] = bb.iloc[:, 2]
    df["bbm"] = bb.iloc[:, 1]
    df["bbl"] = bb.iloc[:, 0]

    # Stochastic for ranging confirmation
    stoch = ta.stoch(h, lo, c, 14, 3, 3)
    df["stoch_k"] = stoch.iloc[:, 0]
    df["stoch_d"] = stoch.iloc[:, 1]

    row  = df.iloc[-1]
    prev = df.iloc[-2]

    close   = float(row["close"])
    bbu     = float(row["bbu"])
    bbl     = float(row["bbl"])
    bbm     = float(row["bbm"])
    atr     = float(row["atr"])
    adx     = float(row["adx"])
    rsi     = float(row["rsi"])
    volume  = float(row["volume"])
    vol_ma  = float(row["vol_ma"])
    stoch_k = float(row["stoch_k"])
    stoch_d = float(row["stoch_d"])

    prev_close = float(prev["close"])
    prev_bbu   = float(prev["bbu"])
    prev_bbl   = float(prev["bbl"])

    vol_ratio = volume / vol_ma if vol_ma > 0 else 1.0
    bb_range  = bbu - bbl
    bb_pos    = (close - bbl) / bb_range * 100 if bb_range > 0 else 50

    signal   = "NONE"
    strength = 0.0
    mode     = "NONE"

    # ── TRENDING regime ──────────────────────────────────────────────────────
    if adx > 28:
        mode = "BREAKOUT"
        # Breakout above upper band with volume
        if close > bbu and prev_close <= prev_bbu and vol_ratio > 1.3:
            signal   = "BUY"
            strength = 0.75
            if vol_ratio > 2.0:
                strength = min(strength + 0.10, 1.0)
            if adx > 40:
                strength = min(strength + 0.05, 1.0)

        # Breakdown below lower band with volume
        elif close < bbl and prev_close >= prev_bbl and vol_ratio > 1.3:
            signal   = "SELL"
            strength = 0.75
            if vol_ratio > 2.0:
                strength = min(strength + 0.10, 1.0)
            if adx > 40:
                strength = min(strength + 0.05, 1.0)

        atr_mult = 2.0   # Wider stop in trending market

    # ── RANGING regime ───────────────────────────────────────────────────────
    elif adx < 22:
        mode = "MEAN_REVERSION"
        # Oversold: RSI < 35, price in lower 20% of BB, stoch bullish cross
        if rsi < 35 and bb_pos < 20 and stoch_k < 25:
            signal   = "BUY"
            strength = 0.70
            if rsi < 30:
                strength = min(strength + 0.10, 1.0)
            if stoch_k > stoch_d:  # Stoch bullish cross
                strength = min(strength + 0.10, 1.0)

        # Overbought: RSI > 65, price in upper 20% of BB, stoch bearish cross
        elif rsi > 65 and bb_pos > 80 and stoch_k > 75:
            signal   = "SELL"
            strength = 0.70
            if rsi > 70:
                strength = min(strength + 0.10, 1.0)
            if stoch_k < stoch_d:  # Stoch bearish cross
                strength = min(strength + 0.10, 1.0)

        atr_mult = 1.5   # Tighter stop in ranging market

    # ── Ambiguous (22 ≤ ADX ≤ 28) — sit out ─────────────────────────────────
    else:
        return {"signal": "NONE", "strength": 0.0,
                "indicators": {"adx": round(adx, 1), "mode": "AMBIGUOUS",
                               "reason": "regime_unclear"}}

    atr_stop_pct = (atr * atr_mult / close) * 100

    return {
        "signal":        signal,
        "strength":      round(strength, 2),
        "stop_loss_pct": round(atr_stop_pct, 3),
        "indicators": {
            "mode":      mode,
            "adx":       round(adx, 1),
            "rsi":       round(rsi, 1),
            "bb_pos":    round(bb_pos, 1),
            "vol_ratio": round(vol_ratio, 2),
            "stoch_k":   round(stoch_k, 1),
            "bbu":       round(bbu, 4),
            "bbl":       round(bbl, 4),
        },
    }
