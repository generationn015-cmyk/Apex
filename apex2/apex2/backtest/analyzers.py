"""Pluggable analyzers (backtrader pattern).

An Analyzer ingests the equity curve + fills after a backtest run and emits
a named result. Run several at once and merge results into a report.

Built-in analyzers cover the metrics in `metrics.py` plus a few extras
(MonthlyReturns, RollingSharpe). User code can subclass `Analyzer` to add
strategy-specific KPIs without touching core engine code.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from .engine import BTFill


@dataclass
class AnalysisResult:
    name: str
    value: Any


class Analyzer(ABC):
    name: str = "base"

    @abstractmethod
    def analyze(
        self,
        equity_curve: list[tuple[pd.Timestamp, float]],
        fills: list[BTFill],
    ) -> AnalysisResult: ...


class SharpeAnalyzer(Analyzer):
    name = "sharpe"

    def __init__(self, bars_per_year: int = 252):
        self.bars_per_year = bars_per_year

    def analyze(self, equity_curve, fills):
        if not equity_curve:
            return AnalysisResult(self.name, 0.0)
        eq = pd.Series({ts: v for ts, v in equity_curve}).sort_index()
        rets = eq.pct_change().dropna()
        std = rets.std(ddof=0)
        sharpe = (rets.mean() / std) * np.sqrt(self.bars_per_year) if std > 0 else 0.0
        return AnalysisResult(self.name, round(float(sharpe), 3))


class DrawdownAnalyzer(Analyzer):
    name = "drawdown"

    def analyze(self, equity_curve, fills):
        if not equity_curve:
            return AnalysisResult(self.name, {"max_dd_pct": 0.0, "longest_dd_days": 0})
        eq = pd.Series({ts: v for ts, v in equity_curve}).sort_index()
        peak = eq.cummax()
        dd = (eq / peak) - 1.0
        max_dd_pct = float(dd.min() * 100)

        in_dd = dd < 0
        groups = (in_dd != in_dd.shift()).cumsum()
        longest = 0
        if in_dd.any():
            longest = int(in_dd.groupby(groups).sum().max())
        return AnalysisResult(self.name, {
            "max_dd_pct": round(max_dd_pct, 2),
            "longest_dd_bars": longest,
        })


class MonthlyReturnsAnalyzer(Analyzer):
    name = "monthly_returns"

    def analyze(self, equity_curve, fills):
        if not equity_curve:
            return AnalysisResult(self.name, {})
        eq = pd.Series({ts: v for ts, v in equity_curve}).sort_index()
        monthly = eq.resample("ME").last().pct_change().dropna()
        return AnalysisResult(self.name, {
            "best_month_pct": round(float(monthly.max() * 100), 2),
            "worst_month_pct": round(float(monthly.min() * 100), 2),
            "winning_months": int((monthly > 0).sum()),
            "losing_months": int((monthly < 0).sum()),
            "avg_month_pct": round(float(monthly.mean() * 100), 3),
        })


class RollingSharpeAnalyzer(Analyzer):
    name = "rolling_sharpe"

    def __init__(self, window: int = 63, bars_per_year: int = 252):
        self.window = window
        self.bars_per_year = bars_per_year

    def analyze(self, equity_curve, fills):
        if not equity_curve or len(equity_curve) < self.window + 1:
            return AnalysisResult(self.name, {"min": 0, "max": 0, "current": 0})
        eq = pd.Series({ts: v for ts, v in equity_curve}).sort_index()
        rets = eq.pct_change().dropna()
        rolling = (rets.rolling(self.window).mean() / rets.rolling(self.window).std()) * np.sqrt(self.bars_per_year)
        rolling = rolling.dropna()
        if rolling.empty:
            return AnalysisResult(self.name, {"min": 0, "max": 0, "current": 0})
        return AnalysisResult(self.name, {
            "min": round(float(rolling.min()), 2),
            "max": round(float(rolling.max()), 2),
            "current": round(float(rolling.iloc[-1]), 2),
        })


@dataclass
class AnalyzerSuite:
    analyzers: list[Analyzer] = field(default_factory=list)

    def run(self, equity_curve, fills) -> dict[str, Any]:
        return {a.name: a.analyze(equity_curve, fills).value for a in self.analyzers}

    @classmethod
    def default(cls) -> "AnalyzerSuite":
        return cls([
            SharpeAnalyzer(),
            DrawdownAnalyzer(),
            MonthlyReturnsAnalyzer(),
            RollingSharpeAnalyzer(),
        ])
