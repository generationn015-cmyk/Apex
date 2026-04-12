"""
Strategy Optimizer Sub-Agent
For each trading agent, monitors paper trade performance over a 48h window.
If the current strategy is not profitable (win rate < 55%), the sub-agent
searches for, backtests, and deploys the most profitable alternative strategy.
"""
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

class StrategyCandidate:
    """A potential strategy for an agent."""
    def __init__(self, name, description, params=None):
        self.name = name
        self.description = description
        self.params = params or {}
        self.backtest_results = {}
        self.score = 0.0

class StrategyOptimizer:
    """Monitors agent performance and rotates strategies."""

    STRATEGY_CATALOG = {
        "sma_crossover": {
            "description": "Simple Moving Average Crossover (Trend Following)",
            "params": {"fast_period": 10, "slow_period": 50},
        },
        "ema_crossover": {
            "description": "Exponential Moving Average Crossover (Faster Trend)",
            "params": {"fast_period": 12, "slow_period": 26},
        },
        "macd_crossover": {
            "description": "MACD Signal Line Crossover (Momentum)",
            "params": {"fast": 12, "slow": 26, "signal": 9},
        },
        "rsi_reversal": {
            "description": "RSI Overbought/Oversold Reversal",
            "params": {"period": 14, "overbought": 70, "oversold": 30},
        },
        "bollinger_breakout": {
            "description": "Bollinger Band Breakout Strategy",
            "params": {"period": 20, "std_dev": 2},
        },
        "stochastic_cross": {
            "description": "Stochastic Oscillator Crossover",
            "params": {"k_period": 14, "d_period": 3},
        },
        "adaptive_dca": {
            "description": "Adaptive Dollar Cost Averaging (Mean Reversion)",
            "params": {"atr_period": 14, "threshold": 2.0},
        },
        "vwap_bounce": {
            "description": "VWAP Bounce Strategy",
            "params": {"period": 20},
        },
        "ichimoku_cloud": {
            "description": "Ichimoku Cloud Trend Following",
            "params": {"tenkan": 9, "kijun": 26, "senkou_b": 52},
        },
        "supertrend": {
            "description": "SuperTrend Volatility Following",
            "params": {"period": 10, "multiplier": 3},
        },
    }

    def __init__(self, min_win_rate=0.55, search_window_hours=48):
        self.min_win_rate = min_win_rate
        self.search_window = timedelta(hours=search_window_hours)
        self.strategy_assignments = {}  # agent_name -> current strategy
        self.last_rotation = {}  # agent_name -> last rotation time

    def should_rotate(self, agent_name, performance_metrics):
        """Check if agent needs a new strategy."""
        win_rate = performance_metrics.get("win_rate", 0) / 100.0
        total_trades = performance_metrics.get("closed", 0)

        # Need minimum trades to judge
        if total_trades < 5:
            return False, "Not enough trades to evaluate"

        if win_rate < self.min_win_rate:
            return True, f"Win rate {win_rate:.0%} below threshold {self.min_win_rate:.0%}"

        return False, f"Win rate {win_rate:.0%} acceptable"

    def get_candidate_strategies(self, exclude=None):
        """Get all strategies except the current one."""
        candidates = []
        for name, info in self.STRATEGY_CATALOG.items():
            if name == exclude:
                continue
            candidates.append(StrategyCandidate(name, info["description"], info["params"]))
        return candidates

    def score_strategy(self, agent_name, strategy_name, backtest_result):
        """Score a strategy based on backtest results."""
        win_rate = backtest_result.get("win_rate", 0)
        profit_factor = backtest_result.get("profit_factor", 0)
        sharpe = backtest_result.get("sharpe", 0)
        max_dd = backtest_result.get("max_drawdown", 1.0)

        # Weighted score: win rate (40%), profit factor (30%), sharpe (20%), low drawdown (10%)
        score = (win_rate * 0.4 +
                 min(profit_factor / 2.0, 1.0) * 0.3 +
                 min(sharpe / 2.0, 1.0) * 0.2 +
                 (1.0 - max_dd) * 0.1)

        return round(score, 3)

    def assign_strategy(self, agent_name, strategy_name, reason=""):
        """Assign a new strategy to an agent."""
        old = self.strategy_assignments.get(agent_name)
        self.strategy_assignments[agent_name] = strategy_name
        self.last_rotation[agent_name] = datetime.now(timezone.utc).isoformat()

        rotation_record = {
            "agent": agent_name,
            "from_strategy": old,
            "to_strategy": strategy_name,
            "rotated_at": self.last_rotation[agent_name],
            "reason": reason,
        }
        return rotation_record

    def get_agent_strategy(self, agent_name):
        return self.strategy_assignments.get(agent_name, "sma_crossover")

    def generate_rotation_report(self):
        """Summary of all strategy rotations and current assignments."""
        report = []
        for agent, strategy in self.strategy_assignments.items():
            rotated_at = self.last_rotation.get(agent, "Never")
            report.append({
                "agent": agent,
                "current_strategy": strategy,
                "strategy_desc": self.STRATEGY_CATALOG.get(strategy, {}).get("description", ""),
                "last_rotated": rotated_at,
            })
        return report
