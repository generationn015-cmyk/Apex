"""
APEX -- BTC 5-Min MACD-Centric Strategy v2
================================================================
7 MACD-derived signals + Window Delta core edge + real-time ticks.
Built for Polymarket BTC Up/Down 5-minute prediction markets.

The edge: Binance BTC spot updates 2-15s faster than Polymarket
reprices. MACD analysis on 1-min candles confirms momentum
direction before entering in the final seconds.

Signal Architecture:
  1. Window Delta       (5-7)  -- core edge: BTC vs 5-min open
  2. MACD Histogram     (2.0)  -- raw histogram direction
  3. MACD Acceleration  (2.0)  -- histogram 2nd derivative (leading)
  4. MACD Cross         (2.5)  -- fresh MACD/signal crossover
  5. MACD Zero Regime   (1.5)  -- above/below zero bias
  6. Fast MACD Confirm  (1.5)  -- short-period (5,13,4) agreement
  7. MACD Volume Flow   (1.5)  -- volume aligned with MACD direction

  Bonus: Tick Trend     (2.0)  -- real-time 2s tick directional bias

Confidence = min(abs(score) / 10.0, 1.0)
Direction  = UP if score > 0, DOWN if score < 0
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class StrategyResult:
    direction: str          # "UP" or "DOWN"
    confidence: float       # 0.0 - 1.0
    score: float            # raw composite score
    indicators: dict        # individual indicator values
    entry_price_est: float  # estimated token cost based on delta
    macd_confirmation: int = 0  # count of non-zero MACD/tick signals (0 = delta-only)


def analyze(
    window_open: float,
    current_price: float,
    candles_1m: list[dict],   # [{open, high, low, close, volume}, ...] last 20+ candles
    tick_prices: list[float] | None = None,  # last ~30 tick prices (2s polling)
) -> StrategyResult:
    """
    Run all 7 MACD signals + Window Delta + Tick Trend.
    Returns directional signal with confidence.
    """
    scores = {}
    details = {}

    # -- 1. Window Delta (weight 5-7) -----------------------------------------
    # Core edge: is BTC above/below the 5-min window open?
    if window_open > 0:
        delta_pct = (current_price - window_open) / window_open * 100
    else:
        delta_pct = 0.0

    abs_delta = abs(delta_pct)
    if abs_delta >= 0.10:
        w = 7.0
    elif abs_delta >= 0.02:
        w = 5.0
    elif abs_delta >= 0.005:
        w = 3.0
    elif abs_delta >= 0.001:
        w = 1.0
    else:
        w = 0.0

    sign = 1.0 if delta_pct >= 0 else -1.0
    scores["window_delta"] = sign * w
    details["delta_pct"] = round(delta_pct, 5)
    details["delta_weight"] = round(w, 1)

    # -- Compute MACD values (needed for signals 2-7) -------------------------
    closes = [c["close"] for c in candles_1m] if candles_1m else []
    volumes = [c.get("volume", 0) for c in candles_1m] if candles_1m else []

    macd_line = None
    signal_line = None
    histogram = None
    macd_history = []
    hist_history = []

    if len(closes) >= 35:  # need 26 + 9 for signal
        macd_line, signal_line, histogram, macd_history, hist_history = _macd_full(closes)

    # Fast MACD (5, 13, 4) for confirmation
    fast_macd_line = None
    fast_signal_line = None
    fast_histogram = None
    if len(closes) >= 17:  # need 13 + 4
        fast_macd_line, fast_signal_line, fast_histogram, _, _ = _macd_full(
            closes, fast=5, slow=13, signal=4
        )

    # -- 2. MACD Histogram Direction (weight 2.0) -----------------------------
    # Positive histogram = bullish momentum, negative = bearish
    macd_hist_score = 0.0
    if histogram is not None:
        price_norm = abs(closes[-1]) * 0.0001 if closes else 1.0
        if price_norm > 0:
            raw = histogram / price_norm
            macd_hist_score = max(-2.0, min(2.0, raw * 1.5))
        details["macd_hist"] = round(histogram, 4)
        details["macd_line"] = round(macd_line, 4)
        details["macd_signal"] = round(signal_line, 4)
    scores["macd_histogram"] = round(macd_hist_score, 3)

    # -- 3. MACD Acceleration (weight 2.0) ------------------------------------
    # Second derivative: is histogram growing or shrinking?
    # This LEADS price -- when histogram starts shrinking, momentum is fading
    macd_accel_score = 0.0
    if len(hist_history) >= 3:
        h_now = hist_history[-1]
        h_prev = hist_history[-2]
        h_prev2 = hist_history[-3]

        accel = h_now - h_prev          # first derivative
        accel_prev = h_prev - h_prev2   # previous first derivative
        jerk = accel - accel_prev       # second derivative (acceleration of acceleration)

        # Growing histogram in the direction of the signal
        if accel > 0 and h_now > 0:
            macd_accel_score = min(2.0, accel / (abs(closes[-1]) * 0.00005) * 1.0)
        elif accel < 0 and h_now < 0:
            macd_accel_score = max(-2.0, accel / (abs(closes[-1]) * 0.00005) * 1.0)
        # Fading histogram = caution (reduce score toward zero)
        elif accel < 0 and h_now > 0:
            macd_accel_score = max(-1.0, accel / (abs(closes[-1]) * 0.00005) * 0.5)
        elif accel > 0 and h_now < 0:
            macd_accel_score = min(1.0, accel / (abs(closes[-1]) * 0.00005) * 0.5)

        details["macd_accel"] = round(accel, 6)
        details["macd_jerk"] = round(jerk, 6)
    scores["macd_acceleration"] = round(macd_accel_score, 3)

    # -- 4. MACD Signal Line Crossover (weight 2.5) ---------------------------
    # Fresh cross of MACD over signal is the strongest MACD signal
    macd_cross_score = 0.0
    if len(hist_history) >= 2:
        h_now = hist_history[-1]
        h_prev = hist_history[-2]

        # Bullish cross: histogram goes from negative to positive
        if h_prev <= 0 and h_now > 0:
            macd_cross_score = 2.5
            details["macd_cross"] = "BULLISH"
        # Bearish cross: histogram goes from positive to negative
        elif h_prev >= 0 and h_now < 0:
            macd_cross_score = -2.5
            details["macd_cross"] = "BEARISH"
        # Near-cross (within 1 candle): weaker signal
        elif h_prev < 0 and h_now < 0 and h_now > h_prev * 0.5:
            macd_cross_score = 0.8  # approaching bullish cross
            details["macd_cross"] = "APPROACHING_BULL"
        elif h_prev > 0 and h_now > 0 and h_now < h_prev * 0.5:
            macd_cross_score = -0.8  # approaching bearish cross
            details["macd_cross"] = "APPROACHING_BEAR"
        else:
            details["macd_cross"] = "NONE"
    scores["macd_cross"] = round(macd_cross_score, 3)

    # -- 5. MACD Zero-Line Regime (weight 1.5) --------------------------------
    # MACD line above zero = bullish regime, below = bearish
    # Stronger when further from zero
    macd_zero_score = 0.0
    if macd_line is not None:
        price_norm = abs(closes[-1]) * 0.0001 if closes else 1.0
        if price_norm > 0:
            distance = macd_line / price_norm
            if macd_line > 0:
                macd_zero_score = min(1.5, distance * 0.8)
            else:
                macd_zero_score = max(-1.5, distance * 0.8)
        details["macd_zero_regime"] = "ABOVE" if macd_line > 0 else "BELOW"
    scores["macd_zero_regime"] = round(macd_zero_score, 3)

    # -- 6. Fast MACD Confirmation (weight 1.5) --------------------------------
    # Short-period MACD (5,13,4) agrees with standard MACD = strong confirmation
    fast_confirm_score = 0.0
    if fast_histogram is not None and histogram is not None:
        # Both histograms same sign = agreement
        if fast_histogram > 0 and histogram > 0:
            fast_confirm_score = 1.5
        elif fast_histogram < 0 and histogram < 0:
            fast_confirm_score = -1.5
        # Disagreement: fast says different from standard = caution
        elif fast_histogram > 0 and histogram < 0:
            fast_confirm_score = 0.3  # fast is leading bullish
        elif fast_histogram < 0 and histogram > 0:
            fast_confirm_score = -0.3  # fast is leading bearish
        details["fast_macd_hist"] = round(fast_histogram, 6)
        details["fast_macd_agrees"] = (fast_histogram > 0) == (histogram > 0)
    scores["fast_macd_confirm"] = round(fast_confirm_score, 3)

    # -- 7. MACD Volume Flow (weight 1.5) -------------------------------------
    # Volume surges aligned with MACD direction = smart money confirmation
    vol_flow_score = 0.0
    if len(candles_1m) >= 6 and histogram is not None:
        recent_vol = sum(volumes[-3:]) / 3 if len(volumes) >= 3 else 0
        prior_vol = sum(volumes[-6:-3]) / 3 if len(volumes) >= 6 else 0

        if prior_vol > 0:
            vol_ratio = recent_vol / prior_vol
            details["vol_ratio"] = round(vol_ratio, 2)

            if vol_ratio > 1.5:
                # High volume -- direction aligned with MACD?
                last_candle_dir = 1.0 if candles_1m[-1]["close"] > candles_1m[-1]["open"] else -1.0
                macd_dir = 1.0 if histogram > 0 else -1.0

                if last_candle_dir == macd_dir:
                    # Volume + candle + MACD all agree = strong flow
                    vol_flow_score = macd_dir * 1.5
                else:
                    # Volume against MACD = possible reversal
                    vol_flow_score = last_candle_dir * 0.3
            elif vol_ratio > 1.2:
                # Moderate volume
                last_dir = 1.0 if candles_1m[-1]["close"] > candles_1m[-1]["open"] else -1.0
                vol_flow_score = last_dir * 0.5
        else:
            details["vol_ratio"] = 0
    scores["macd_volume_flow"] = round(vol_flow_score, 3)

    # -- Bonus: Real-Time Tick Trend (weight 2) --------------------------------
    tick_score = 0.0
    if tick_prices and len(tick_prices) >= 10:
        ups = sum(1 for i in range(1, len(tick_prices)) if tick_prices[i] > tick_prices[i-1])
        downs = sum(1 for i in range(1, len(tick_prices)) if tick_prices[i] < tick_prices[i-1])
        total_ticks = ups + downs
        if total_ticks > 0:
            up_pct = ups / total_ticks
            move_pct = abs(tick_prices[-1] - tick_prices[0]) / tick_prices[0] * 100
            if up_pct > 0.60 and move_pct > 0.005:
                tick_score = 2.0
            elif up_pct > 0.55 and move_pct > 0.003:
                tick_score = 1.0
            elif up_pct < 0.40 and move_pct > 0.005:
                tick_score = -2.0
            elif up_pct < 0.45 and move_pct > 0.003:
                tick_score = -1.0
            details["tick_up_pct"] = round(up_pct * 100, 1)
            details["tick_move_pct"] = round(move_pct, 4)
        else:
            details["tick_up_pct"] = 50.0
    scores["tick_trend"] = round(tick_score, 3)

    # -- Composite Score -------------------------------------------------------
    total_score = sum(scores.values())
    confidence = min(abs(total_score) / 10.0, 1.0)
    direction = "UP" if total_score > 0 else "DOWN"

    # -- MACD/Tick Confirmation Count ------------------------------------------
    # Count how many non-delta signals actually fired (non-zero)
    _confirm_keys = ["macd_histogram", "macd_acceleration", "macd_cross",
                     "macd_zero_regime", "fast_macd_confirm", "macd_volume_flow",
                     "tick_trend"]
    macd_confirm_count = sum(1 for k in _confirm_keys if abs(scores.get(k, 0)) > 0.01)

    # -- Token Price Estimate --------------------------------------------------
    entry_price_est = _estimate_token_price(abs_delta)

    details["scores"] = {k: round(v, 2) for k, v in scores.items()}
    details["total_score"] = round(total_score, 2)
    details["macd_confirmation"] = macd_confirm_count

    return StrategyResult(
        direction=direction,
        confidence=confidence,
        score=total_score,
        indicators=details,
        entry_price_est=entry_price_est,
        macd_confirmation=macd_confirm_count,
    )


def _estimate_token_price(abs_delta_pct: float) -> float:
    """
    Estimate what the winning token costs based on BTC's delta from open.
    Larger moves = more expensive tokens = smaller edge.
    Based on empirical Polymarket pricing data.
    """
    if abs_delta_pct < 0.005:
        return 0.50
    elif abs_delta_pct < 0.02:
        return 0.55
    elif abs_delta_pct < 0.05:
        return 0.65
    elif abs_delta_pct < 0.10:
        return 0.80
    elif abs_delta_pct < 0.15:
        return 0.92
    else:
        return 0.97


# -- Technical Indicator Helpers -----------------------------------------------

def _ema(data: list[float], period: int) -> float:
    """Exponential Moving Average."""
    if len(data) < period:
        return data[-1] if data else 0.0
    k = 2.0 / (period + 1)
    ema = sum(data[:period]) / period
    for val in data[period:]:
        ema = val * k + ema * (1 - k)
    return ema


def _macd_full(
    closes: list[float],
    fast: int = 12, slow: int = 26, signal: int = 9,
) -> tuple[float | None, float | None, float | None, list[float], list[float]]:
    """
    Full MACD computation returning:
      macd_line, signal_line, histogram, macd_history, histogram_history
    """
    if len(closes) < slow + signal:
        return None, None, None, [], []

    # Build MACD history for signal line computation
    macd_history = []
    for i in range(slow, len(closes) + 1):
        subset = closes[:i]
        ef = _ema(subset, fast)
        es = _ema(subset, slow)
        macd_history.append(ef - es)

    if len(macd_history) < signal:
        return macd_history[-1] if macd_history else None, None, None, macd_history, []

    # Build signal line history for histogram history
    hist_history = []
    for i in range(signal, len(macd_history) + 1):
        sig_val = _ema(macd_history[:i], signal)
        hist_history.append(macd_history[i - 1] - sig_val)

    macd_line = macd_history[-1]
    signal_line = _ema(macd_history, signal)
    histogram = macd_line - signal_line

    return macd_line, signal_line, histogram, macd_history, hist_history
