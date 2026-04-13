"""
SENTINEL — EMA Alignment + Squeeze Agent  (BTC/USDT, stable trend assets)

What was wrong before:
  - Triple EMA alignment fires constantly during slow drift
  - Partial alignment (EMA8 > EMA21 only) = 60% strength = too many weak trades

Fixes:
  - Add Keltner Channel squeeze: only trade when price breaks out of low-volatility compression
    (BB inside KC = squeeze = coiled spring before a move)
  - Require PERFECT alignment only (not partial) for trade entry
  - EMA slope filter: EMA8 must be rising (bull) or falling (bear) — no flat entries
  - Minimum price distance from EMA21 (0.3%) to avoid hugging the line
  - ATR-based stops
"""
import pandas_ta as ta
import pandas as pd


def _ema_slope(series: pd.Series, period: int = 3) -> float:
    """Slope of last `period` values normalised by current price."""
    if len(series) < period + 1:
        return 0.0
    recent = series.iloc[-(period+1):]
    return float((recent.iloc[-1] - recent.iloc[0]) / recent.iloc[0])


def analyze_SENTINEL(df: pd.DataFrame, df_4h: pd.DataFrame | None = None) -> dict | None:
    if df is None or len(df) < 60:
        return None

    c  = df["close"]
    h  = df["high"]
    lo = df["low"]

    df = df.copy()
    df["ema8"]   = ta.ema(c, 8)
    df["ema21"]  = ta.ema(c, 21)
    df["ema50"]  = ta.ema(c, 50)
    df["atr"]    = ta.atr(h, lo, c, 14)
    df["adx"]    = ta.adx(h, lo, c, 14)["ADX_14"]

    # Bollinger Bands (squeeze component)
    bb = ta.bbands(c, 20, 2.0)
    df["bb_upper"] = bb.iloc[:, 2]
    df["bb_lower"] = bb.iloc[:, 0]

    # Keltner Channels (squeeze component)
    kc = ta.kc(h, lo, c, 20, 1.5)
    df["kc_upper"] = kc.iloc[:, 2]
    df["kc_lower"] = kc.iloc[:, 0]

    row  = df.iloc[-1]
    prev = df.iloc[-2]

    ema8   = float(row["ema8"])
    ema21  = float(row["ema21"])
    ema50  = float(row["ema50"])
    close  = float(row["close"])
    atr    = float(row["atr"])
    adx    = float(row["adx"])

    bb_up  = float(row["bb_upper"])
    bb_lo  = float(row["bb_lower"])
    kc_up  = float(row["kc_upper"])
    kc_lo  = float(row["kc_lower"])

    # Previous row for squeeze-release detection
    prev_bb_up = float(prev["bb_upper"])
    prev_bb_lo = float(prev["bb_lower"])
    prev_kc_up = float(prev["kc_upper"])
    prev_kc_lo = float(prev["kc_lower"])

    # ── Squeeze detection ────────────────────────────────────────────────────
    # Squeeze ON:  BB entirely inside KC
    # Squeeze OFF: BB breaks outside KC (the release — this is the trade)
    squeeze_was_on  = prev_bb_up <= prev_kc_up and prev_bb_lo >= prev_kc_lo
    squeeze_now_off = not (bb_up <= kc_up and bb_lo >= kc_lo)
    squeeze_release = squeeze_was_on and squeeze_now_off

    # Current squeeze state
    in_squeeze = bb_up <= kc_up and bb_lo >= kc_lo

    # ── EMA alignment ────────────────────────────────────────────────────────
    bull_perfect = ema8 > ema21 > ema50 and close > ema8
    bear_perfect = ema8 < ema21 < ema50 and close < ema8

    # ── EMA slope ────────────────────────────────────────────────────────────
    slope8 = _ema_slope(df["ema8"], 3)
    slope_bull = slope8 > 0.001   # EMA8 rising meaningfully
    slope_bear = slope8 < -0.001  # EMA8 falling meaningfully

    # ── Price distance from EMA21 (avoid hugging) ───────────────────────────
    dist_pct = abs(close - ema21) / ema21 * 100
    if dist_pct < 0.3:
        return {"signal": "NONE", "strength": 0.0,
                "indicators": {"dist_pct": round(dist_pct, 3), "reason": "too_close_to_ema21"}}

    # ── ADX gate ─────────────────────────────────────────────────────────────
    if adx < 22:
        return {"signal": "NONE", "strength": 0.0,
                "indicators": {"adx": round(adx, 1), "reason": "no_trend"}}

    # ── Signal logic ─────────────────────────────────────────────────────────
    signal   = "NONE"
    strength = 0.0

    if bull_perfect and slope_bull:
        signal   = "BUY"
        strength = 0.55              # persistent alignment — below 0.65 threshold
        if squeeze_release:
            strength = 0.90          # squeeze breakout — tradeable event
        elif not in_squeeze:
            strength = min(strength + 0.05, 1.0)
        if adx > 35:
            strength = min(strength + 0.05, 1.0)

    elif bear_perfect and slope_bear:
        signal   = "SELL"
        strength = 0.55              # persistent alignment — below 0.65 threshold
        if squeeze_release:
            strength = 0.90          # squeeze breakout — tradeable event
        elif not in_squeeze:
            strength = min(strength + 0.05, 1.0)
        if adx > 35:
            strength = min(strength + 0.05, 1.0)

    # No partial alignment trades
    if signal == "NONE" and not (bull_perfect or bear_perfect):
        return {"signal": "NONE", "strength": 0.0,
                "indicators": {"adx": round(adx, 1), "reason": "partial_alignment_rejected"}}

    atr_stop_pct = (atr * 1.5 / close) * 100

    return {
        "signal":        signal,
        "strength":      round(strength, 2),
        "stop_loss_pct": round(atr_stop_pct, 3),
        "indicators": {
            "ema8":           round(ema8, 4),
            "ema21":          round(ema21, 4),
            "ema50":          round(ema50, 4),
            "adx":            round(adx, 1),
            "squeeze_release": squeeze_release,
            "in_squeeze":     in_squeeze,
            "slope8":         round(slope8 * 100, 4),
            "dist_pct":       round(dist_pct, 3),
        },
    }
