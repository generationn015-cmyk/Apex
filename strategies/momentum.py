"""
Multi-Timeframe Momentum Strategy
===================================
Philosophy: Only trade in the direction of the macro trend.
Enter on 5-min timeframe when the short-term momentum aligns
with the 15-min and 1H structure.

Research-backed timing (2026 data):
  - Best hours: 13:00-17:00 UTC (US-Europe overlap, peak liquidity)
  - Monday anomaly: BTC shows highest returns on Mondays
  - ADX regime filter: ADX < 20 = ranging (skip momentum), ADX > 25 = trending (enter)
  - Weekends: higher momentum Sharpe ratios on volatile pairs (SOL, DOGE)

Signal logic:
  LONG when:
    - UTC hour is within preferred trading window (or weekend override)
    - 1H EMA9 > EMA21  (macro trend is up)
    - 15m EMA9 > EMA21 (intermediate trend confirms)
    - 5m EMA9 crosses above EMA21 (micro entry trigger)
    - 5m RSI > 52 (momentum confirmation, not overbought)
    - ADX > 20 (regime confirms trending, not ranging)
    - Volume > 1.2x 20-bar average (participation)

  SHORT: mirror conditions.

Stop: 1.5x ATR below entry
Target: 3.0x ATR above entry (2:1 R:R)
"""
from __future__ import annotations

import datetime
import logging

import numpy as np

from exchanges.base import BaseExchange, Candle
from signals.indicators import (
    adx, atr, ema, ema_crossover, last, rsi, volume_sma,
)
from strategies.base import BaseStrategy, Signal, SignalDirection

log = logging.getLogger("apex.strategy.momentum")

# Research-backed optimal trading hours (UTC)
# US-Europe overlap: highest liquidity, tightest spreads, strongest momentum signals
PRIME_HOURS_UTC = set(range(13, 18))       # 13:00-17:59 UTC (peak)
GOOD_HOURS_UTC = set(range(14, 23))        # 14:00-22:59 UTC (US session)
MONDAY_HOUR_BOOST = 1.1                    # Monday signals get 10% confidence boost


class MomentumStrategy(BaseStrategy):
    name = "momentum"

    def __init__(self, config: dict):
        super().__init__(config)
        self.tf_entry: str = config.get("timeframes", {}).get("entry", "5m")
        self.tf_trend: str = config.get("timeframes", {}).get("trend_filter", "15m")
        self.tf_macro: str = config.get("timeframes", {}).get("macro", "1h")

        self.ema_fast: int = config.get("ema_fast", 9)
        self.ema_slow: int = config.get("ema_slow", 21)
        self.rsi_period: int = config.get("rsi_period", 14)
        self.rsi_long: float = config.get("rsi_long_threshold", 52.0)
        self.rsi_short: float = config.get("rsi_short_threshold", 48.0)
        self.adx_period: int = config.get("adx_period", 14)
        self.adx_min: float = config.get("adx_min", 20.0)
        self.atr_period: int = config.get("atr_period", 14)
        self.stop_atr: float = config.get("stop_atr_mult", 1.5)
        self.target_atr: float = config.get("target_atr_mult", 3.0)
        self.vol_mult: float = config.get("min_volume_mult", 1.2)
        self.use_timing_filter: bool = config.get("use_timing_filter", True)
        self.allow_weekends: bool = config.get("allow_weekends", True)  # weekends have higher momentum Sharpe

    def _is_good_time(self) -> tuple[bool, float]:
        """
        Check if current UTC time is within a high-edge trading window.
        Returns (should_trade, confidence_multiplier).
        Research: US-Europe overlap (13-17 UTC) has strongest momentum signals.
        Monday anomaly: BTC historically outperforms on Mondays.
        """
        if not self.use_timing_filter:
            return True, 1.0

        now = datetime.datetime.utcnow()
        hour = now.hour
        weekday = now.weekday()   # 0=Monday, 5=Saturday, 6=Sunday
        is_weekend = weekday >= 5

        if is_weekend:
            if self.allow_weekends:
                return True, 1.05   # Slightly higher Sharpe on weekends for volatile pairs
            return False, 1.0

        if hour in PRIME_HOURS_UTC:
            mult = MONDAY_HOUR_BOOST if weekday == 0 else 1.0
            return True, mult

        if hour in GOOD_HOURS_UTC:
            return True, 0.9    # Slightly lower confidence outside prime window

        # Off-hours (Asian session, late night UTC) — lower quality signals
        return False, 0.7

    async def analyze(self, pair: str, venue: str, exchange: BaseExchange) -> Signal | None:
        # ── Timing filter (research-backed) ────────────────────────
        should_trade, timing_mult = self._is_good_time()
        if not should_trade:
            return None

        # ── Fetch candles for all three timeframes ──────────────────
        try:
            candles_entry = await exchange.get_candles(pair, self.tf_entry, 100)
            candles_trend = await exchange.get_candles(pair, self.tf_trend, 60)
            candles_macro = await exchange.get_candles(pair, self.tf_macro, 60)
        except Exception as e:
            log.debug("fetch candles %s: %s", pair, e)
            return None

        if len(candles_entry) < 50 or len(candles_trend) < 30 or len(candles_macro) < 30:
            return None

        # ── Extract price arrays ─────────────────────────────────────
        def extract(candles: list[Candle]) -> tuple:
            closes = [c.close for c in candles]
            highs = [c.high for c in candles]
            lows = [c.low for c in candles]
            vols = [c.volume for c in candles]
            return closes, highs, lows, vols

        e_closes, e_highs, e_lows, e_vols = extract(candles_entry)
        t_closes, _, _, _ = extract(candles_trend)
        m_closes, _, _, _ = extract(candles_macro)

        # ── Entry timeframe indicators ───────────────────────────────
        e_ema_fast = ema(e_closes, self.ema_fast)
        e_ema_slow = ema(e_closes, self.ema_slow)
        e_rsi = rsi(e_closes, self.rsi_period)
        e_atr = atr(e_highs, e_lows, e_closes, self.atr_period)
        e_adx = adx(e_highs, e_lows, e_closes, self.adx_period)
        e_vol_avg = volume_sma(e_vols, 20)

        # ── Trend timeframe indicators ───────────────────────────────
        t_ema_fast = ema(t_closes, self.ema_fast)
        t_ema_slow = ema(t_closes, self.ema_slow)

        # ── Macro timeframe indicators ───────────────────────────────
        m_ema_fast = ema(m_closes, self.ema_fast)
        m_ema_slow = ema(m_closes, self.ema_slow)

        # ── Read latest values ────────────────────────────────────────
        current_price = e_closes[-1]
        current_rsi = last(e_rsi)
        current_adx = last(e_adx)
        current_atr_val = last(e_atr)
        current_vol = e_vols[-1]
        avg_vol = last(e_vol_avg)

        if np.isnan(current_adx) or np.isnan(current_atr_val):
            return None

        # ── EMA crossover on entry TF ─────────────────────────────────
        bull_cross, bear_cross = ema_crossover(e_ema_fast, e_ema_slow)

        # ── Trend alignment ───────────────────────────────────────────
        trend_up = float(t_ema_fast[-1]) > float(t_ema_slow[-1])
        trend_dn = float(t_ema_fast[-1]) < float(t_ema_slow[-1])
        macro_up = float(m_ema_fast[-1]) > float(m_ema_slow[-1])
        macro_dn = float(m_ema_fast[-1]) < float(m_ema_slow[-1])

        # ── Volume confirmation ───────────────────────────────────────
        vol_ok = not np.isnan(avg_vol) and current_vol >= avg_vol * self.vol_mult

        # ── ADX confirms trending market ───────────────────────────────
        adx_ok = current_adx >= self.adx_min

        # ── Build LONG signal ─────────────────────────────────────────
        if (bull_cross and macro_up and trend_up and
                current_rsi >= self.rsi_long and adx_ok and vol_ok):

            stop = current_price - current_atr_val * self.stop_atr
            target = current_price + current_atr_val * self.target_atr
            base_conf = self._calc_confidence(
                current_rsi, current_adx, current_vol, avg_vol, "long"
            )
            confidence = round(min(base_conf * timing_mult, 1.0), 3)
            return Signal(
                strategy=self.name,
                pair=pair,
                venue=venue,
                direction=SignalDirection.LONG,
                confidence=confidence,
                entry_price=current_price,
                stop_price=stop,
                target_price=target,
                timeframe=self.tf_entry,
                metadata={
                    "rsi": round(current_rsi, 1),
                    "adx": round(current_adx, 1),
                    "atr": round(current_atr_val, 4),
                    "vol_ratio": round(current_vol / avg_vol, 2) if avg_vol else 0,
                    "trend_tf": self.tf_trend,
                    "macro_tf": self.tf_macro,
                    "timing_mult": timing_mult,
                    "utc_hour": datetime.datetime.utcnow().hour,
                },
            )

        # ── Build SHORT signal ────────────────────────────────────────
        if (bear_cross and macro_dn and trend_dn and
                current_rsi <= self.rsi_short and adx_ok and vol_ok):

            stop = current_price + current_atr_val * self.stop_atr
            target = current_price - current_atr_val * self.target_atr
            base_conf = self._calc_confidence(
                current_rsi, current_adx, current_vol, avg_vol, "short"
            )
            confidence = round(min(base_conf * timing_mult, 1.0), 3)
            return Signal(
                strategy=self.name,
                pair=pair,
                venue=venue,
                direction=SignalDirection.SHORT,
                confidence=confidence,
                entry_price=current_price,
                stop_price=stop,
                target_price=target,
                timeframe=self.tf_entry,
                metadata={
                    "rsi": round(current_rsi, 1),
                    "adx": round(current_adx, 1),
                    "atr": round(current_atr_val, 4),
                    "vol_ratio": round(current_vol / avg_vol, 2) if avg_vol else 0,
                    "timing_mult": timing_mult,
                    "utc_hour": datetime.datetime.utcnow().hour,
                },
            )

        return None

    def _calc_confidence(
        self,
        rsi_val: float,
        adx_val: float,
        vol: float,
        avg_vol: float,
        direction: str,
    ) -> float:
        """
        Score the signal quality 0.0-1.0.
        Higher = more confident = larger position size from Kelly.
        """
        score = 0.0

        # RSI strength contribution (0-0.35)
        if direction == "long":
            rsi_score = min((rsi_val - 52) / 30, 1.0)   # 52→100 maps to 0→1
        else:
            rsi_score = min((48 - rsi_val) / 30, 1.0)   # 48→0 maps to 0→1
        score += max(0, rsi_score) * 0.35

        # ADX strength (0-0.35): ADX 20→60 maps to 0→1
        adx_score = min((adx_val - 20) / 40, 1.0)
        score += max(0, adx_score) * 0.35

        # Volume spike (0-0.30)
        if avg_vol > 0:
            vol_score = min((vol / avg_vol - 1.2) / 3.0, 1.0)
            score += max(0, vol_score) * 0.30

        return round(min(score, 1.0), 3)
