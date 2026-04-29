"""Walk-forward parameter optimization with Optuna.

The pattern:
  1. Split history into N rolling windows: each has IS (in-sample) and OOS (out).
  2. For each window: optimize params on IS (Optuna search), evaluate on OOS.
  3. Report OOS Sharpe distribution. If OOS Sharpe is materially below IS Sharpe,
     the strategy is overfit — reject.

This is the gold standard for parameter robustness. A strategy that only works
with one specific param combination is curve-fit. Walk-forward catches it.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable

import pandas as pd

from .engine import BacktestEngine
from .metrics import compute_metrics

log = logging.getLogger("apex2.backtest.walkforward")


@dataclass
class WalkForwardWindow:
    is_start: datetime
    is_end: datetime
    oos_start: datetime
    oos_end: datetime
    best_params: dict = field(default_factory=dict)
    is_sharpe: float = 0.0
    oos_sharpe: float = 0.0
    oos_metrics: dict = field(default_factory=dict)


@dataclass
class WalkForwardResult:
    windows: list[WalkForwardWindow] = field(default_factory=list)

    def summary(self) -> dict:
        if not self.windows:
            return {}
        is_sharpes = [w.is_sharpe for w in self.windows]
        oos_sharpes = [w.oos_sharpe for w in self.windows]
        return {
            "windows": len(self.windows),
            "avg_is_sharpe": round(sum(is_sharpes) / len(is_sharpes), 3),
            "avg_oos_sharpe": round(sum(oos_sharpes) / len(oos_sharpes), 3),
            "min_oos_sharpe": round(min(oos_sharpes), 3),
            "max_oos_sharpe": round(max(oos_sharpes), 3),
            "is_oos_decay_pct": round(
                100 * (1 - sum(oos_sharpes) / sum(is_sharpes))
                if sum(is_sharpes) > 0 else 0,
                1,
            ),
            "oos_positive_pct": round(
                100 * sum(1 for s in oos_sharpes if s > 0) / len(oos_sharpes), 1
            ),
        }


# Strategy factory: takes a params dict, returns a callable strategy.
StrategyFactory = Callable[[dict], Callable]


def walk_forward(
    bars_by_symbol: dict[str, pd.DataFrame],
    strategy_factory: StrategyFactory,
    bt_cfg,
    param_search_space: dict,
    is_years: float = 2.0,
    oos_years: float = 0.5,
    step_years: float = 0.5,
    n_trials: int = 30,
    sampler_seed: int = 42,
) -> WalkForwardResult:
    """Run walk-forward optimization.

    param_search_space: dict mapping param name to one of:
        ("int", low, high) | ("float", low, high) | ("choices", [v1, v2, ...])

    Returns WalkForwardResult with one window per slide.
    """
    try:
        import optuna
    except ImportError:
        raise RuntimeError("Optuna not installed. pip install optuna")

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    all_ts = sorted(set().union(*(df.index for df in bars_by_symbol.values())))
    if len(all_ts) < 252:
        raise ValueError("not enough history for walk-forward")
    full_start, full_end = all_ts[0].to_pydatetime(), all_ts[-1].to_pydatetime()

    is_td = timedelta(days=int(is_years * 365.25))
    oos_td = timedelta(days=int(oos_years * 365.25))
    step_td = timedelta(days=int(step_years * 365.25))

    result = WalkForwardResult()
    cur = full_start
    while cur + is_td + oos_td <= full_end:
        win = WalkForwardWindow(
            is_start=cur,
            is_end=cur + is_td,
            oos_start=cur + is_td,
            oos_end=cur + is_td + oos_td,
        )

        def objective(trial: "optuna.Trial") -> float:
            params = {}
            for name, spec in param_search_space.items():
                if spec[0] == "int":
                    params[name] = trial.suggest_int(name, spec[1], spec[2])
                elif spec[0] == "float":
                    params[name] = trial.suggest_float(name, spec[1], spec[2])
                elif spec[0] == "choices":
                    params[name] = trial.suggest_categorical(name, spec[1])
                else:
                    raise ValueError(f"unknown spec type {spec[0]}")
            strat = strategy_factory(params)
            engine = BacktestEngine(bt_cfg)
            state = engine.run(bars_by_symbol, strat, start=win.is_start, end=win.is_end)
            m = compute_metrics(state.equity_curve, state.fills)
            return m.sharpe

        sampler = optuna.samplers.TPESampler(seed=sampler_seed)
        study = optuna.create_study(direction="maximize", sampler=sampler)
        study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

        win.best_params = dict(study.best_params)
        win.is_sharpe = float(study.best_value)

        # Evaluate on OOS.
        strat = strategy_factory(win.best_params)
        state = BacktestEngine(bt_cfg).run(bars_by_symbol, strat, start=win.oos_start, end=win.oos_end)
        oos_m = compute_metrics(state.equity_curve, state.fills)
        win.oos_sharpe = oos_m.sharpe
        win.oos_metrics = {
            "cagr_pct": oos_m.cagr_pct,
            "max_dd_pct": oos_m.max_drawdown_pct,
            "trades": oos_m.num_trades,
            "win_rate_pct": oos_m.win_rate_pct,
        }
        log.info("WF window %s..%s: IS=%.2f OOS=%.2f params=%s",
                 win.is_start.date(), win.oos_end.date(),
                 win.is_sharpe, win.oos_sharpe, win.best_params)
        result.windows.append(win)
        cur = cur + step_td

    return result
