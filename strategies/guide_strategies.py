"""Guide Strategies — Grid, DCA, Momentum, Stat Arb, and Funding Rate Arb.

These are the 6 strategies from the Trading Bot Master Guide,
implemented as signal generators compatible with the paper trading engine.
"""
import numpy as np
import pandas as pd


class BaseStrategy:
    """Base class for all strategies."""
    name = "base"
    description = ""

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        raise NotImplementedError


# ============================================================
# STRATEGY 1: AI-Enhanced Grid Trading
# Buy at fixed intervals below current price, sell at intervals above.
# Captures profit on every oscillation in ranging markets.
# ============================================================
class GridStrategy(BaseStrategy):
    name = "Grid Trading"
    description = "Places buy/sell orders at fixed intervals. Captures profit on oscillations."

    def __init__(self, num_grids: int = 20, range_pct: float = 0.05):
        self.num_grids = num_grids
        self.range_pct = range_pct

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """Generate signals based on grid level touches."""
        close = df['Close']
        n = len(close)
        signal = pd.Series(0, index=df.index, dtype=int)

        # Use rolling window for adaptive grid ranges
        window = 50  # Look back ~2 days at hourly

        for i in range(window, n):
            window_high = close.iloc[i-window:i].max()
            window_low = close.iloc[i-window:i].min()
            center = (window_high + window_low) / 2
            half_range = (window_high - window_low) / 2

            if half_range == 0:
                continue

            # Grid levels
            grid_spacing = (2 * self.range_pct * center) / self.num_grids
            lower_bound = center - self.range_pct * center
            upper_bound = center + self.range_pct * center

            # Position based on where price is in range
            normalized_pos = (close.iloc[i] - lower_bound) / (self.range_pct * center * 2)

            if normalized_pos < 0.2:
                # Near bottom of range — buy signal
                signal.iloc[i] = 1
            elif normalized_pos > 0.8:
                # Near top of range — sell signal
                signal.iloc[i] = -1

        return signal


# ============================================================
# STRATEGY 2: Adaptive DCA (Dollar-Cost Averaging)
# Buy at fixed intervals, increase size on fear/oversold, sell on take-profit.
# ============================================================
class ADCAStrategy(BaseStrategy):
    name = "Adaptive DCA"
    description = "DCA with RSI gate. Buy when RSI < 45, sell on take-profit."

    def __init__(self, rsi_threshold: float = 45.0, take_profit_pct: float = 0.025):
        self.rsi_threshold = rsi_threshold
        self.take_profit_pct = take_profit_pct

    def _rsi(self, close: pd.Series, period: int = 14) -> pd.Series:
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(period).mean()
        rs = gain / loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        close = df['Close']
        rsi = self._rsi(close)
        signal = pd.Series(0, index=df.index, dtype=int)

        # Track position state
        position = 0
        entry_price = 0

        for i in range(14, len(rsi)):
            if position == 0 and rsi.iloc[i] < self.rsi_threshold:
                # Buy signal: accumulate when oversold
                signal.iloc[i] = 1
                position = 1
                entry_price = close.iloc[i]
            elif position == 1 and close.iloc[i] >= entry_price * (1 + self.take_profit_pct):
                # Sell signal: take profit
                signal.iloc[i] = -1
                position = 0

        return signal


# ============================================================
# STRATEGY 3: Market Making
# Place buy and sell limit orders around mid-price, capture spread.
# Simplified for paper testing: buy when price dips below MA, sell when above.
# ============================================================
class MarketMakingStrategy(BaseStrategy):
    name = "Market Making"
    description = "Places buy/sell around mid-price. Captures spread. Best on zero-fee DEX."

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        close = df['Close']
        mid = close.rolling(20).mean()
        std = close.rolling(20).std()
        spread = 0.001  # 10 bps

        signal = pd.Series(0, index=df.index, dtype=int)

        buy_line = mid - std * spread * 100
        sell_line = mid + std * spread * 100

        for i in range(20, len(close)):
            if close.iloc[i] <= buy_line.iloc[i] and not np.isnan(buy_line.iloc[i]):
                signal.iloc[i] = 1
            elif close.iloc[i] >= sell_line.iloc[i] and not np.isnan(sell_line.iloc[i]):
                signal.iloc[i] = -1

        return signal


# ============================================================
# STRATEGY 4: Statistical Arbitrage (Stat Arb)
# Exploit spread divergence between correlated assets (BTC vs ETH, ETH vs SOL).
# For paper testing without cross-pair data, simplified to single-asset mean reversion.
# ============================================================
class StatArbStrategy(BaseStrategy):
    name = "Stat Arb"
    description = "Mean reversion via Z-score. Enter when price deviates 2 std from mean, exit at 0.5."

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        close = df['Close']
        window = 20
        sma = close.rolling(window).mean()
        std = close.rolling(window).std()
        spread = close - sma
        z_score = spread / std.replace(0, np.nan)

        signal = pd.Series(0, index=df.index, dtype=int)

        for i in range(window, len(z_score)):
            if z_score.iloc[i] > 2.0:
                signal.iloc[i] = -1  # Price too high — sell
            elif z_score.iloc[i] < -2.0:
                signal.iloc[i] = 1   # Price too low — buy
            elif abs(z_score.iloc[i]) < 0.5:
                signal.iloc[i] = 0   # Converged — flat

        return signal


# ============================================================
# STRATEGY 5: Momentum / Trend Following (Guide Signal Stack)
# EMA(9)/EMA(21) cross + RSI filter + volume confirmation
# ============================================================
class MomentumStrategy(BaseStrategy):
    name = "Momentum Trend"
    description = "EMA 9/21 crossover with RSI 50-70 filter and volume confirmation."

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        close = df['Close']
        volume = df['Volume']

        # EMA signals
        ema9 = close.ewm(span=9, adjust=False).mean()
        ema21 = close.ewm(span=21, adjust=False).mean()

        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))

        # Volume
        vol_ma = volume.rolling(20).mean()
        high_vol = volume > vol_ma * 1.2

        # Signal stack: ALL conditions must be met (conservative)
        signal = pd.Series(0, index=df.index, dtype=int)
        bull = (ema9 > ema21) & (rsi > 50) & (rsi < 70) & high_vol
        bear = (ema9 < ema21) | (rsi > 70)

        signal[bull] = 1
        signal[bear] = -1

        return signal


# ============================================================
# STRATEGY 6: Funding Rate Arbitrage
# For paper testing: simulate delta-neutral position capture.
# Since we don't have real funding rates, model it as:
# When price is stable (low volatility), earn "funding" yield.
# When volatile, avoid.
# ============================================================
class FundingRateStrategy(BaseStrategy):
    name = "Funding Rate Arb"
    description = "Delta-neutral arbitrage. Earn funding yield when market is stable."

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        close = df['Close']
        window = 20

        # Volatility filter
        returns = close.pct_change()
        vol = returns.rolling(window).std()
        avg_vol = vol.mean()

        # If volatility is low (<70% of average low), "earn funding"
        # High vol = pause position
        signal = pd.Series(0, index=df.index, dtype=int)

        low_vol = vol < (avg_vol * 0.7)

        signal[low_vol] = 1   # In position during calm periods
        signal[~low_vol] = -1  # Flat during high volatility

        return signal


# Registry of guide strategies
GUIDE_STRATEGIES = [
    GridStrategy(),
    ADCAStrategy(),
    MarketMakingStrategy(),
    StatArbStrategy(),
    MomentumStrategy(),
    FundingRateStrategy(),
]

GUIDE_STRATEGY_MAP = {s.name: s for s in GUIDE_STRATEGIES}
