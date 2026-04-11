"""
Bollinger Band Squeeze Breakout Strategy
==========================================
Philosophy: Volatility compression precedes explosive moves.
When the market coils into a tight range (BB squeeze), energy
builds. The first candle to close convincingly outside the bands
— with volume — is the breakout signal.

Entry: Close above upper BB (long) or below lower BB (short)
Volume: Must be ≥ 2x 20-bar average to confirm genuine breakout
Stop:  ATR * 1.0 from entry (tight, right outside bands)
Target: Band width * 2.0 projected from breakout level
"""
from __future__ import annotations

import logging

import numpy as np

from exchanges.base import BaseExchange, Candle
from signals.indicators import (
    atr, bollinger_bands, bb_width, detect_squeeze,
    is_breakout, last, volume_sma,
)
from strategies.base import BaseStrategy, Signal, SignalDirection

log = logging.getLogger("apex.strategy.breakout")


class BreakoutStrategy(BaseStrategy):
    name = "breakout"

    def __init__(self, config: dict):
        super().__init__(config)
        self.timeframes: list[str] = config.get("timeframes", ["15m", "1h"])
        self.bb_period: int = config.get("bb_period", 20)
        self.bb_std: float = config.get("bb_std", 2.0)
        self.squeeze_threshold: float = config.get("squeeze_threshold_pct", 1.5)
        self.volume_mult: float = config.get("volume_mult", 2.0)
        self.atr_period: int = config.get("atr_period", 14)
        self.stop_atr: float = config.get("stop_atr_mult", 1.0)
        self.target_bb_mult: float = config.get("target_bb_mult", 2.0)

    async def analyze(self, pair: str, venue: str, exchange: BaseExchange) -> Signal | None:
        for timeframe in self.timeframes:
            signal = await self._analyze_tf(pair, venue, exchange, timeframe)
            if signal:
                return signal
        return None

    async def _analyze_tf(
        self, pair: str, venue: str, exchange: BaseExchange, timeframe: str
    ) -> Signal | None:
        try:
            candles = await exchange.get_candles(pair, timeframe, 100)
        except Exception as e:
            log.debug("fetch candles %s/%s: %s", pair, timeframe, e)
            return None

        if len(candles) < self.bb_period + 10:
            return None

        closes = [c.close for c in candles]
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        volumes = [c.volume for c in candles]

        upper, mid, lower = bollinger_bands(closes, self.bb_period, self.bb_std)
        width = bb_width(upper, mid, lower)
        vol_avg = volume_sma(volumes, 20)
        atr_vals = atr(highs, lows, closes, self.atr_period)

        current_price = closes[-1]
        current_atr = last(atr_vals)
        current_width = last(width)
        current_upper = last(upper)
        current_lower = last(lower)
        current_mid = last(mid)

        if any(np.isnan(v) for v in [current_atr, current_width, current_upper, current_lower]):
            return None

        # ── Was there a squeeze building? ─────────────────────────────
        # Check last 5 bars for squeeze condition
        squeeze_lookback = min(10, len(width))
        recent_width = width[-squeeze_lookback:]
        had_squeeze = not np.all(np.isnan(recent_width)) and (
            np.nanmin(recent_width) <= self.squeeze_threshold
        )

        if not had_squeeze:
            return None

        # ── Is this a breakout candle? ────────────────────────────────
        bull_break, bear_break = is_breakout(
            closes, upper, lower, volumes, vol_avg, self.volume_mult
        )

        band_width_val = current_upper - current_lower

        if bull_break:
            stop = current_price - current_atr * self.stop_atr
            target = current_price + band_width_val * self.target_bb_mult
            confidence = self._calc_confidence(
                volumes[-1], last(vol_avg), current_width, "long"
            )
            return Signal(
                strategy=self.name,
                pair=pair,
                venue=venue,
                direction=SignalDirection.LONG,
                confidence=confidence,
                entry_price=current_price,
                stop_price=stop,
                target_price=target,
                timeframe=timeframe,
                metadata={
                    "bb_width": round(current_width, 3),
                    "bb_upper": round(current_upper, 2),
                    "bb_lower": round(current_lower, 2),
                    "vol_ratio": round(volumes[-1] / last(vol_avg), 2) if last(vol_avg) > 0 else 0,
                    "squeeze": True,
                },
            )

        if bear_break:
            stop = current_price + current_atr * self.stop_atr
            target = current_price - band_width_val * self.target_bb_mult
            confidence = self._calc_confidence(
                volumes[-1], last(vol_avg), current_width, "short"
            )
            return Signal(
                strategy=self.name,
                pair=pair,
                venue=venue,
                direction=SignalDirection.SHORT,
                confidence=confidence,
                entry_price=current_price,
                stop_price=stop,
                target_price=target,
                timeframe=timeframe,
                metadata={
                    "bb_width": round(current_width, 3),
                    "bb_upper": round(current_upper, 2),
                    "bb_lower": round(current_lower, 2),
                    "vol_ratio": round(volumes[-1] / last(vol_avg), 2) if last(vol_avg) > 0 else 0,
                    "squeeze": True,
                },
            )

        return None

    def _calc_confidence(
        self, vol: float, avg_vol: float, width: float, direction: str
    ) -> float:
        score = 0.0
        # Volume quality (0-0.5)
        if avg_vol > 0:
            vol_ratio = vol / avg_vol
            vol_score = min((vol_ratio - self.volume_mult) / 3.0, 1.0)
            score += max(0, vol_score) * 0.5
        # Squeeze tightness (0-0.5): tighter = higher quality
        if width > 0:
            squeeze_score = min((self.squeeze_threshold - width) / self.squeeze_threshold + 1, 1.0)
            score += max(0, squeeze_score) * 0.5
        return round(min(score, 1.0), 3)
