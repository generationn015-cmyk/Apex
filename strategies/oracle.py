"""
ORACLE — MACD Momentum Agent  (ETH/USDT, SOL/USDT)

What was wrong before:
  - MACD histogram cross fires constantly, even on tiny histogram values
  - No RSI gate → caught overbought/oversold entries
  - MACD cross below zero line = weak signal (trend already turning)

Fixes:
  - Require MACD cross to happen ABOVE zero line for BUY (BELOW for SELL)
    → only trade when momentum AND direction align
  - RSI confirmation: BUY only when RSI 40–65 (not overbought on entry)
    SELL only when RSI 35–60 (not oversold on entry)
  - Minimum histogram magnitude (> 0.05% of price) to filter micro-crosses
  - ATR-based stops
  - ADX > 20 light filter (MACD already filters ranging, just sanity check)
"""
import pandas_ta as ta
import pandas as pd


def analyze_ORACLE(df: pd.DataFrame, df_4h: pd.DataFrame | None = None) -> dict | None:
    if df is None or len(df) < 60:
        return None

    c  = df["close"]
    h  = df["high"]
    lo = df["low"]

    df = df.copy()
    macd_df   = ta.macd(c, 12, 26, 9)
    df["macd"]        = macd_df.iloc[:, 0]
    df["macd_signal"] = macd_df.iloc[:, 1]
    df["macd_hist"]   = macd_df.iloc[:, 2]
    df["rsi"]  = ta.rsi(c, 14)
    df["adx"]  = ta.adx(h, lo, c, 14)["ADX_14"]
    df["atr"]  = ta.atr(h, lo, c, 14)

    row  = df.iloc[-1]
    prev = df.iloc[-2]

    macd_h  = float(row["macd_hist"])
    macd_hp = float(prev["macd_hist"])
    macd_l  = float(row["macd"])
    rsi     = float(row["rsi"])
    adx     = float(row["adx"])
    atr     = float(row["atr"])
    close   = float(row["close"])

    # ── Gate: ADX ───────────────────────────────────────────────────────────
    if adx < 20:
        return {"signal": "NONE", "strength": 0.0,
                "indicators": {"adx": round(adx, 1), "reason": "no_trend"}}

    # ── Gate: Histogram must be meaningful ──────────────────────────────────
    min_hist = close * 0.0005   # 0.05% of price
    if abs(macd_h) < min_hist:
        return {"signal": "NONE", "strength": 0.0,
                "indicators": {"macd_hist": round(macd_h, 6), "reason": "micro_cross"}}

    # ── Crosses ─────────────────────────────────────────────────────────────
    cross_up = macd_h > 0 and macd_hp <= 0
    cross_dn = macd_h < 0 and macd_hp >= 0

    # ── Signal logic ─────────────────────────────────────────────────────────
    signal   = "NONE"
    strength = 0.0

    if cross_up and macd_l > 0 and 40 <= rsi <= 65:
        # Fresh bullish cross ABOVE zero line + RSI not overbought
        signal   = "BUY"
        strength = 0.90
    elif cross_dn and macd_l < 0 and 35 <= rsi <= 60:
        # Fresh bearish cross BELOW zero line + RSI not oversold
        signal   = "SELL"
        strength = 0.90
    elif macd_h > 0 and macd_l > 0 and rsi < 60:
        # Holding bullish territory (continuation)
        signal   = "BUY"
        strength = 0.55
    elif macd_h < 0 and macd_l < 0 and rsi > 40:
        signal   = "SELL"
        strength = 0.55

    # ADX bonus
    if signal != "NONE" and adx > 30:
        strength = min(strength + 0.05, 1.0)

    # HTF alignment bonus
    htf_aligned = False
    if df_4h is not None and len(df_4h) >= 26:
        df_4h = df_4h.copy()
        m4 = ta.macd(df_4h["close"], 12, 26, 9)
        htf_hist = float(m4.iloc[-1, 2])   # 4h histogram
        if signal == "BUY" and htf_hist > 0:
            htf_aligned = True
            strength = min(strength + 0.05, 1.0)
        elif signal == "SELL" and htf_hist < 0:
            htf_aligned = True
            strength = min(strength + 0.05, 1.0)

    atr_stop_pct = (atr * 1.5 / close) * 100

    return {
        "signal":        signal,
        "strength":      round(strength, 2),
        "stop_loss_pct": round(atr_stop_pct, 3),
        "indicators": {
            "macd_line":   round(macd_l, 6),
            "macd_hist":   round(macd_h, 6),
            "rsi":         round(rsi, 1),
            "adx":         round(adx, 1),
            "cross":       "BULLISH" if cross_up else "BEARISH" if cross_dn else "NONE",
            "zero_line":   "ABOVE" if macd_l > 0 else "BELOW",
            "htf_aligned": htf_aligned,
        },
    }
