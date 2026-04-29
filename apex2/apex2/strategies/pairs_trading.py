"""Statistical arbitrage on cointegrated sector ETF pairs.

Strategy:
  - Pre-defined high-correlation pairs (e.g. XLF/KRE, XLK/SOXX, IWM/IJR).
  - Compute hedge ratio via 60-day rolling OLS: log(A) = beta * log(B) + alpha.
  - Spread = log(A) - beta * log(B). Z-score over 30 days.
  - Entry when |z| > entry_z (default 2.0): long underperformer, short outperformer.
  - Exit when |z| < exit_z (default 0.5) or |z| > stop_z (default 4.0, blow-out).
  - Equal dollar legs sized so each leg = max_position_pct/2.

Edge thesis:
  - Sector ETFs in the same industry track each other tightly.
  - Short-term divergences (news, flow imbalances) revert within days/weeks.
  - Pair construction provides built-in market-neutrality.

Risk:
  - Cointegration breakdown (regime change). Mitigated by stop_z exit.
  - Crowded trades (other stat-arb funds). Use less obvious pairs.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..backtest.engine import BTOrder, BTState
from .base import Strategy


@dataclass
class _OpenPair:
    long_sym: str
    short_sym: str
    entry_z: float


class PairsTrading(Strategy):
    name = "pairs_trading"

    def __init__(self, ctx):
        super().__init__(ctx)
        p = ctx.params
        # Each pair is [sym_a, sym_b]. We trade the spread log(A) - beta*log(B).
        self.pairs: list[list[str]] = list(p.get("pairs", [["XLF", "KRE"], ["XLK", "SOXX"]]))
        self.lookback = int(p.get("lookback_days", 60))
        self.zscore_window = int(p.get("zscore_window", 30))
        self.entry_z = float(p.get("entry_z", 2.0))
        self.exit_z = float(p.get("exit_z", 0.5))
        self.stop_z = float(p.get("stop_z", 4.0))
        self._open: dict[str, _OpenPair] = {}     # key = "A_B"

    def on_bar(self, state: BTState, ts: pd.Timestamp, bars: dict[str, pd.DataFrame]):
        orders: list[BTOrder] = []
        equity = state.mark_to_market(bars, ts)
        leg_dollars = equity * (self.ctx.max_position_pct / 100.0) / 2.0

        for pair in self.pairs:
            a, b = pair[0], pair[1]
            df_a = self.history(bars, a, ts)
            df_b = self.history(bars, b, ts)
            if df_a is None or df_b is None:
                continue
            min_bars = max(self.lookback, self.zscore_window) + 5
            if len(df_a) < min_bars or len(df_b) < min_bars:
                continue

            # Align on common dates.
            joined = pd.concat([df_a["close"].rename("a"), df_b["close"].rename("b")], axis=1).dropna()
            if len(joined) < min_bars:
                continue

            log_a = np.log(joined["a"])
            log_b = np.log(joined["b"])

            # Rolling OLS hedge ratio over `lookback`.
            window = joined.iloc[-self.lookback:]
            la = np.log(window["a"]).values
            lb = np.log(window["b"]).values
            beta = float(np.polyfit(lb, la, 1)[0])
            if not np.isfinite(beta) or abs(beta) < 0.1 or abs(beta) > 10:
                continue

            spread = log_a - beta * log_b
            z = (spread - spread.rolling(self.zscore_window).mean()) / spread.rolling(self.zscore_window).std()
            if z.empty or pd.isna(z.iloc[-1]):
                continue
            current_z = float(z.iloc[-1])

            key = f"{a}_{b}"
            open_pair = self._open.get(key)

            # Exit logic.
            if open_pair is not None:
                if abs(current_z) < self.exit_z or abs(current_z) > self.stop_z:
                    pos_long = state.positions.get(open_pair.long_sym)
                    pos_short = state.positions.get(open_pair.short_sym)
                    if pos_long and pos_long.qty > 0:
                        orders.append(BTOrder(ts, open_pair.long_sym, "sell", pos_long.qty,
                                              reason="pairs_exit"))
                    if pos_short and pos_short.qty < 0:
                        orders.append(BTOrder(ts, open_pair.short_sym, "buy", -pos_short.qty,
                                              reason="pairs_exit"))
                    self._open.pop(key, None)
                continue

            # Entry logic.
            if abs(current_z) >= self.entry_z and abs(current_z) < self.stop_z:
                px_a = float(joined["a"].iloc[-1])
                px_b = float(joined["b"].iloc[-1])
                if px_a <= 0 or px_b <= 0:
                    continue
                qty_a = int(leg_dollars // px_a)
                qty_b = int(leg_dollars // px_b)
                if qty_a <= 0 or qty_b <= 0:
                    continue

                # If z > 0: A is overperforming → short A, long B.
                # If z < 0: A is underperforming → long A, short B.
                if current_z > 0:
                    long_sym, long_qty = b, qty_b
                    short_sym, short_qty = a, qty_a
                else:
                    long_sym, long_qty = a, qty_a
                    short_sym, short_qty = b, qty_b

                orders.append(BTOrder(ts, long_sym, "buy", long_qty, reason=f"pairs_entry_z={current_z:.2f}"))
                orders.append(BTOrder(ts, short_sym, "sell", short_qty, reason=f"pairs_entry_z={current_z:.2f}"))
                self._open[key] = _OpenPair(long_sym=long_sym, short_sym=short_sym, entry_z=current_z)

        return orders
