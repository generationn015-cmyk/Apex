"""
APEX — Risk Manager (Wolf-ported)
All agents route through this before any trade.

Key improvements over old version:
  - RollingCircuitBreaker: 10-trade window (not consecutive count) — much harder to game
  - Kelly Criterion with volatility dampener — stops over-sizing in choppy regimes
  - AgentPnLTracker: annualised Sharpe + Sortino per agent
  - Portfolio daily loss cap (3%) + hard kill switch (40% drawdown)
"""
import logging
from collections import deque
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger("apex.risk")

# ── Module-level state (survives re-instantiation across hot reloads) ──────────
_breakers: dict[str, "RollingCircuitBreaker"] = {}
_trackers: dict[str, "AgentPnLTracker"]       = {}

TRADES_PER_DAY = 6   # ~1 trade per 4h per agent — used for annualisation


# ── Rolling Circuit Breaker ────────────────────────────────────────────────────
class RollingCircuitBreaker:
    """
    Trips when win-rate over the last N trades falls below a floor.
    Much more robust than a simple consecutive-loss counter.

    Ported from wolf/risk_engine.py — adapted for crypto perps (no expiry).
    """
    WINDOW       = 10      # number of trades in rolling window
    MIN_WR       = 0.35    # 35% floor — below this = systematic failure
    PAUSE_HOURS  = 6       # cooldown before re-evaluation

    def __init__(self, name: str):
        self.name    = name
        self._trades: deque[bool] = deque(maxlen=self.WINDOW)  # True=win
        self._paused_until: Optional[datetime] = None

    def record(self, won: bool):
        self._trades.append(won)
        if len(self._trades) >= self.WINDOW:
            if self.rolling_wr() < self.MIN_WR:
                self._paused_until = datetime.now(timezone.utc) + timedelta(hours=self.PAUSE_HOURS)
                logger.warning(
                    f"CircuitBreaker [{self.name}] tripped — "
                    f"WR={self.rolling_wr():.1%} over {len(self._trades)} trades. "
                    f"Paused {self.PAUSE_HOURS}h."
                )

    def is_paused(self) -> bool:
        if self._paused_until is None:
            return False
        if datetime.now(timezone.utc) >= self._paused_until:
            self._paused_until = None
            self._trades.clear()   # fresh window after cooldown
            logger.info(f"CircuitBreaker [{self.name}] reset after cooldown")
            return False
        return True

    def rolling_wr(self) -> float:
        if not self._trades:
            return 1.0
        return sum(self._trades) / len(self._trades)

    def remaining_hours(self) -> float:
        if not self._paused_until:
            return 0.0
        delta = self._paused_until - datetime.now(timezone.utc)
        return max(0.0, delta.total_seconds() / 3600)

    def reset(self):
        self._trades.clear()
        self._paused_until = None


# ── Per-agent P&L Tracker (Sharpe / Sortino) ──────────────────────────────────
class AgentPnLTracker:
    """
    Tracks rolling returns and computes annualised Sharpe + Sortino.
    Uses a 50-trade window — enough for a statistically meaningful signal.
    """
    WINDOW = 50

    def __init__(self, name: str):
        self.name     = name
        self._returns: deque[float] = deque(maxlen=self.WINDOW)
        self.total_pnl = 0.0
        self.trades    = 0

    def record(self, pnl_pct: float):
        """pnl_pct: fractional return on capital, e.g. +0.02 = +2%"""
        self._returns.append(pnl_pct)
        self.total_pnl += pnl_pct
        self.trades    += 1

    def sharpe(self) -> float:
        if len(self._returns) < 5:
            return 0.0
        import statistics
        mu  = statistics.mean(self._returns)
        std = statistics.stdev(self._returns)
        if std == 0:
            return 0.0
        return round(mu / std * (TRADES_PER_DAY * 365) ** 0.5, 2)

    def sortino(self) -> float:
        if len(self._returns) < 5:
            return 0.0
        import statistics
        mu          = statistics.mean(self._returns)
        downside    = [r for r in self._returns if r < 0]
        if not downside:
            return float("inf")
        downside_std = statistics.stdev(downside) if len(downside) > 1 else abs(downside[0])
        if downside_std == 0:
            return 0.0
        return round(mu / downside_std * (TRADES_PER_DAY * 365) ** 0.5, 2)

    def stats(self) -> dict:
        return {
            "trades":     self.trades,
            "total_pnl":  round(self.total_pnl, 4),
            "sharpe":     self.sharpe(),
            "sortino":    self.sortino(),
            "window_wr":  (
                round(sum(1 for r in self._returns if r > 0) / len(self._returns) * 100, 1)
                if self._returns else 0.0
            ),
        }


# ── Main Risk Manager ──────────────────────────────────────────────────────────
class RiskManager:
    """
    Unified gatekeeper for all APEX agents.

    Position sizing: half-Kelly with volatility dampener
    Circuit breaker: rolling 10-trade WR floor (35%)
    Daily cap: 3% portfolio loss before all agents pause
    Kill switch: 40% drawdown from peak capital
    """

    # Kelly / sizing params
    KELLY_FRACTION   = 0.5      # half-Kelly for safety
    MIN_VOL_SCALAR   = 0.40     # scale down in high-vol / choppy regimes
    MAX_POSITION_PCT = 0.20     # never more than 20% of capital in one trade

    # Portfolio-level guards
    DAILY_LOSS_CAP   = 0.03     # 3% portfolio daily loss → all agents pause
    KILL_SWITCH_PCT  = 0.40     # 40% drawdown from peak → hard stop

    def __init__(self, starting_capital: float = 100.0):
        self._start_cap    = starting_capital
        self._peak_cap     = starting_capital
        self._capital      = starting_capital
        self._day_start_cap = starting_capital
        self._last_day_reset = datetime.now(timezone.utc).date()

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _breaker(self, agent: str) -> RollingCircuitBreaker:
        if agent not in _breakers:
            _breakers[agent] = RollingCircuitBreaker(agent)
        return _breakers[agent]

    def _tracker(self, agent: str) -> AgentPnLTracker:
        if agent not in _trackers:
            _trackers[agent] = AgentPnLTracker(agent)
        return _trackers[agent]

    def _reset_day_if_needed(self):
        today = datetime.now(timezone.utc).date()
        if today != self._last_day_reset:
            self._day_start_cap  = self._capital
            self._last_day_reset = today

    # ── Gate check ────────────────────────────────────────────────────────────
    def can_trade(self, agent_name: str, volatility_score: float = 50) -> tuple[bool, str]:
        """
        Returns (allowed: bool, reason: str).
        volatility_score: 0-100 (ADX or custom vol metric).
        """
        self._reset_day_if_needed()

        # 1. Kill switch — portfolio-level
        drawdown = (self._peak_cap - self._capital) / self._peak_cap
        if drawdown >= self.KILL_SWITCH_PCT:
            return False, f"Kill switch: {drawdown:.1%} drawdown from peak"

        # 2. Daily loss cap
        day_pnl_pct = (self._capital - self._day_start_cap) / self._day_start_cap
        if day_pnl_pct <= -self.DAILY_LOSS_CAP:
            return False, f"Daily loss cap: {day_pnl_pct:.1%} today"

        # 3. Circuit breaker for this agent
        breaker = self._breaker(agent_name)
        if breaker.is_paused():
            return False, (
                f"CircuitBreaker paused — "
                f"WR too low over last {RollingCircuitBreaker.WINDOW} trades. "
                f"{breaker.remaining_hours():.1f}h remaining"
            )

        # 4. Capital check
        if self._capital <= 0:
            return False, "No capital remaining"

        return True, "Approved"

    # ── Position sizing ───────────────────────────────────────────────────────
    def calculate_position_size(
        self,
        capital: float,
        win_rate: float,
        avg_win_pct: float,
        avg_loss_pct: float,
        volatility_score: float = 50,
    ) -> tuple[float, str]:
        """
        Half-Kelly with volatility dampener.

        Returns (size_usd, note).
        win_rate:      0–1 estimated WR for this setup
        avg_win_pct:   average win as fraction of position (e.g. 0.02 = 2%)
        avg_loss_pct:  average loss as fraction (positive number)
        volatility_score: 0-100, higher = choppier
        """
        if avg_loss_pct <= 0 or capital <= 0:
            return 0.0, "Invalid inputs"

        # Kelly fraction: f = (b·p - q) / b
        b = avg_win_pct / avg_loss_pct   # odds ratio
        p = win_rate
        q = 1 - p
        kelly = (b * p - q) / b
        kelly = max(0.0, kelly)

        # Half-Kelly
        fraction = kelly * self.KELLY_FRACTION

        # Volatility dampener (0-100 → scalar 0.40–1.0)
        if volatility_score >= 80:
            vol_scalar = self.MIN_VOL_SCALAR          # very choppy
        elif volatility_score >= 65:
            vol_scalar = 0.55
        elif volatility_score >= 50:
            vol_scalar = 0.70
        elif volatility_score >= 35:
            vol_scalar = 0.85
        else:
            vol_scalar = 1.0                          # trending — full Kelly

        fraction *= vol_scalar

        # Cap at MAX_POSITION_PCT
        fraction = min(fraction, self.MAX_POSITION_PCT)

        size_usd = round(capital * fraction, 2)
        note     = f"Kelly={kelly:.2%} half={fraction/vol_scalar:.2%} vol_scalar={vol_scalar}"
        return size_usd, note

    # ── Stop loss ─────────────────────────────────────────────────────────────
    def get_stop_loss(self, entry_price: float, direction: str,
                      atr: Optional[float] = None, atr_mult: float = 1.5) -> float:
        """ATR-based stop if atr provided, else 2% hard stop."""
        if atr and atr > 0:
            stop_dist = atr * atr_mult
        else:
            stop_dist = entry_price * 0.02

        if direction == "BUY":
            return round(entry_price - stop_dist, 6)
        else:
            return round(entry_price + stop_dist, 6)

    # ── Record outcomes ───────────────────────────────────────────────────────
    def record_win(self, agent_name: str, pnl_usd: float = 0.0):
        self._capital    += pnl_usd
        self._peak_cap    = max(self._peak_cap, self._capital)
        self._breaker(agent_name).record(True)
        if self._capital > 0:
            self._tracker(agent_name).record(pnl_usd / self._capital)

    def record_loss(self, agent_name: str, pnl_usd: float = 0.0):
        """pnl_usd: negative number (loss amount)"""
        self._capital += pnl_usd   # pnl_usd is negative
        self._breaker(agent_name).record(False)
        if self._capital > 0:
            self._tracker(agent_name).record(pnl_usd / self._capital)

    # ── Status / stats ────────────────────────────────────────────────────────
    def get_stats(self) -> dict:
        self._reset_day_if_needed()
        drawdown  = (self._peak_cap - self._capital) / self._peak_cap
        day_pnl   = (self._capital - self._day_start_cap) / self._day_start_cap
        agents    = {k: v.stats() for k, v in _trackers.items()}

        # Portfolio Sharpe: weighted average across agents
        sharpe_vals  = [v["sharpe"]  for v in agents.values() if v["trades"] >= 5]
        sortino_vals = [v["sortino"] for v in agents.values() if v["trades"] >= 5]

        return {
            "capital":          round(self._capital, 2),
            "peak_capital":     round(self._peak_cap, 2),
            "drawdown_pct":     round(drawdown * 100, 2),
            "day_pnl_pct":      round(day_pnl * 100, 2),
            "kill_switch_active": drawdown >= self.KILL_SWITCH_PCT,
            "daily_cap_active": day_pnl <= -self.DAILY_LOSS_CAP,
            "portfolio_sharpe": round(sum(sharpe_vals)  / len(sharpe_vals),  2) if sharpe_vals  else 0.0,
            "portfolio_sortino":round(sum(sortino_vals) / len(sortino_vals), 2) if sortino_vals else 0.0,
            "agents":           agents,
        }

    def get_agent_status(self, agent_name: str) -> dict:
        breaker = self._breaker(agent_name)
        tracker = self._tracker(agent_name)
        return {
            "paused":           breaker.is_paused(),
            "remaining_hours":  breaker.remaining_hours(),
            "rolling_wr":       round(breaker.rolling_wr() * 100, 1),
            "window_trades":    len(breaker._trades),
            **tracker.stats(),
        }
