"""
APEX Web Dashboard
==================
Gamified real-time trading terminal served at http://localhost:8080

Architecture:
  - FastAPI serves index.html + a /ws WebSocket endpoint
  - Bot calls push_state() each cycle; state is broadcast to all connected browsers
  - Frontend auto-reconnects if the connection drops

Features:
  - Live balance, P&L, win rate with flash-on-change animations
  - Open positions with unrealized P&L and trailing stop indicator
  - Signal feed showing confluence tier, confidence, execution status
  - Trader level system (Intern → Market Master) with XP bar
  - Monthly target progress bar toward $2,500
  - Achievement badges (unlocked live as milestones are hit)
  - Win streak tracker
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

log = logging.getLogger("apex.webdash")

try:
    import uvicorn
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.responses import HTMLResponse
    FASTAPI_OK = True
except ImportError:
    FASTAPI_OK = False
    log.warning("fastapi/uvicorn not installed — run: pip install fastapi 'uvicorn[standard]'")

if TYPE_CHECKING:
    from execution.engine import ExecutionEngine
    from risk.manager import RiskManager


_STATIC_DIR = Path(__file__).parent / "static"

# ── Gamification config ───────────────────────────────────────────────────────

LEVELS = [
    (1, "Intern",         0,    10),
    (2, "Junior Analyst", 10,   30),
    (3, "Market Analyst", 30,   60),
    (4, "Senior Trader",  60,  100),
    (5, "Fund Manager",  100,  200),
    (6, "Market Master", 200, 9999),
]

ACHIEVEMENTS: dict[str, tuple[str, str, str]] = {
    # key: (icon, display_name, description)
    "first_win":       ("🏆", "First Blood",       "First winning trade"),
    "win_streak_3":    ("🔥", "On Fire",            "3 consecutive wins"),
    "win_streak_5":    ("💥", "Unstoppable",         "5 consecutive wins"),
    "tier3_trade":     ("⚡", "Triple Threat",       "Executed a Tier 3 confluence trade"),
    "tier4_trade":     ("🌋", "Max Overdrive",       "Executed a Tier 4 confluence trade"),
    "precision":       ("🎯", "Precision",           "Win rate >70% with 10+ trades"),
    "diamond_hands":   ("💎", "Diamond Hands",       "Held a trade all the way to target"),
    "milestone_1k":    ("💼", "Portfolio Manager",   "Balance reached $1,000"),
    "milestone_2500":  ("🏦", "Fund Manager",        "Balance reached $2,500 — monthly target!"),
    "century_club":    ("📊", "Century Club",        "100 trades executed"),
}


class WebDashboard:
    """
    Manages the FastAPI web server and WebSocket state broadcasts.
    Attach to the bot via attach() then call start() in start().
    Call push_state() each cycle to refresh all connected browsers.
    Call log_signal() for each processed signal to populate the feed.
    """

    def __init__(
        self,
        port: int = 8080,
        starting_balance: float = 500.0,
        monthly_target: float = 2500.0,
    ):
        self.port = port
        self.starting_balance = starting_balance
        self.monthly_target = monthly_target

        self._clients: list[WebSocket] = []
        self._execution: "ExecutionEngine | None" = None
        self._risk: "RiskManager | None" = None
        self._signal_buffer: list[dict] = []  # Rolling last-20 signals
        self._unlocked: set[str] = set()
        self._server_task: asyncio.Task | None = None

    # ── Public API ────────────────────────────────────────────────────

    def attach(self, execution: "ExecutionEngine", risk: "RiskManager") -> None:
        self._execution = execution
        self._risk = risk

    def log_signal(
        self,
        pair: str,
        direction: str,
        confidence: float,
        rr: float,
        score: float,
        executed: bool,
        confluence_tier: int = 1,
    ) -> None:
        """Record a signal into the rolling buffer for the feed panel."""
        import datetime
        self._signal_buffer.append({
            "time":      datetime.datetime.utcnow().strftime("%H:%M"),
            "pair":      pair,
            "direction": direction,
            "confidence": round(confidence * 100, 1),
            "rr":        round(rr, 2),
            "score":     round(score, 3),
            "executed":  executed,
            "tier":      confluence_tier,
        })
        if len(self._signal_buffer) > 20:
            self._signal_buffer.pop(0)

    async def push_state(self) -> None:
        """Build the current bot state snapshot and send it to every browser."""
        if not self._clients or not self._risk or not self._execution:
            return
        state = self._build_state()
        payload = json.dumps(state)
        dead = []
        for ws in self._clients:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            if ws in self._clients:
                self._clients.remove(ws)

    def start(self) -> None:
        """Spin up the uvicorn server as a background asyncio task."""
        if not FASTAPI_OK:
            log.warning("Web dashboard disabled — install fastapi + uvicorn[standard]")
            return
        app = self._build_app()
        config = uvicorn.Config(app, host="0.0.0.0", port=self.port, log_level="warning")
        server = uvicorn.Server(config)
        self._server_task = asyncio.create_task(server.serve())
        log.info("=" * 50)
        log.info("  Web dashboard: http://localhost:%d", self.port)
        log.info("=" * 50)

    # ── State builder ─────────────────────────────────────────────────

    def _build_state(self) -> dict:
        risk = self._risk
        exe  = self._execution
        stats = risk.get_stats()

        balance    = stats["balance"]
        starting   = risk.starting_balance
        total_pnl  = balance - starting
        total_pct  = (total_pnl / starting * 100) if starting else 0.0

        level, level_name, level_progress = _get_level(total_pct)
        win_streak = _compute_win_streak(exe)

        # Achievement evaluation
        all_trades    = exe.get_all_trades()
        closed        = [t for t in all_trades if t.status == "closed"]
        wins          = [t for t in closed if t.pnl > 0]
        target_hits   = [t for t in closed if t.close_reason == "TARGET_HIT"]
        max_tier      = max((t.confluence_tier for t in all_trades), default=1)

        self._eval_achievements(
            balance=balance,
            wins=len(wins),
            total_trades=len(closed),
            win_streak=win_streak,
            max_tier=max_tier,
            target_hits=len(target_hits),
            win_rate=stats["win_rate"],
        )

        # Open trades
        open_trades = []
        for t in exe.get_open_trades():
            open_trades.append({
                "id":          t.trade_id,
                "pair":        t.signal.pair,
                "direction":   t.signal.direction.value,
                "entry":       t.entry_fill_price,
                "stop":        t.signal.stop_price,
                "target":      t.signal.target_price,
                "pnl":         round(t.pnl, 2),
                "trail_active": t.dynamic_stop > 0,
                "trail_stop":  round(t.dynamic_stop, 4) if t.dynamic_stop > 0 else None,
                "tier":        t.confluence_tier,
                "opened_at":   t.opened_at,
            })

        return {
            "type":           "state_update",
            "ts":             time.time(),
            "mode":           "PAPER" if exe.paper_mode else "LIVE",
            # Financials
            "balance":        round(balance, 2),
            "starting":       round(starting, 2),
            "daily_pnl":      round(stats["daily_pnl"], 2),
            "daily_pnl_pct":  round(stats["daily_pnl_pct"], 2),
            "total_pnl":      round(total_pnl, 2),
            "total_pnl_pct":  round(total_pct, 2),
            "drawdown_pct":   round(stats["drawdown_pct"], 2),
            "win_rate":       round(stats["win_rate"], 1),
            "trades_today":   stats["trades_today"],
            "open_positions": stats["open_positions"],
            "halted":         stats["halted"],
            # Gamification
            "level":          level,
            "level_name":     level_name,
            "level_progress": round(level_progress, 3),
            "win_streak":     win_streak,
            "score":          _performance_score(stats["win_rate"], len(wins), len(closed)),
            "achievements":   list(self._unlocked),
            "target":         self.monthly_target,
            "target_progress": round(min(balance / self.monthly_target, 1.0), 3),
            # Live data
            "open_trades":    open_trades,
            "signals":        list(self._signal_buffer[-10:]),
        }

    def _eval_achievements(
        self, balance, wins, total_trades, win_streak, max_tier, target_hits, win_rate
    ) -> None:
        checks = {
            "first_win":      wins >= 1,
            "win_streak_3":   win_streak >= 3,
            "win_streak_5":   win_streak >= 5,
            "tier3_trade":    max_tier >= 3,
            "tier4_trade":    max_tier >= 4,
            "precision":      win_rate > 70 and total_trades >= 10,
            "diamond_hands":  target_hits >= 1,
            "milestone_1k":   balance >= 1000,
            "milestone_2500": balance >= 2500,
            "century_club":   total_trades >= 100,
        }
        for key, unlocked in checks.items():
            if unlocked and key not in self._unlocked:
                self._unlocked.add(key)
                icon, name, _ = ACHIEVEMENTS[key]
                log.info("ACHIEVEMENT UNLOCKED: %s %s", icon, name)

    # ── FastAPI app ───────────────────────────────────────────────────

    def _build_app(self) -> "FastAPI":
        app = FastAPI(title="APEX Trading Terminal")

        @app.get("/", response_class=HTMLResponse)
        async def index():
            return HTMLResponse((_STATIC_DIR / "index.html").read_text())

        @app.get("/api/state")
        async def api_state():
            if self._risk and self._execution:
                return self._build_state()
            return {"error": "bot not ready"}

        @app.websocket("/ws")
        async def ws_endpoint(ws: WebSocket):
            await ws.accept()
            self._clients.append(ws)
            log.debug("WS client connected (%d total)", len(self._clients))
            # Send current state immediately on connect
            if self._risk and self._execution:
                try:
                    await ws.send_text(json.dumps(self._build_state()))
                except Exception:
                    pass
            try:
                while True:
                    try:
                        await asyncio.wait_for(ws.receive_text(), timeout=25)
                    except asyncio.TimeoutError:
                        await ws.send_text(json.dumps({"type": "ping"}))
            except (WebSocketDisconnect, Exception):
                pass
            finally:
                if ws in self._clients:
                    self._clients.remove(ws)
                log.debug("WS client disconnected (%d total)", len(self._clients))

        return app


# ── Pure helpers (no class state) ────────────────────────────────────────────

def _get_level(pnl_pct: float) -> tuple[int, str, float]:
    for level, name, lo, hi in LEVELS:
        if pnl_pct < hi:
            progress = (pnl_pct - lo) / (hi - lo) if (hi - lo) > 0 else 1.0
            return level, name, max(0.0, min(1.0, progress))
    return 6, "Market Master", 1.0


def _compute_win_streak(exe: "ExecutionEngine") -> int:
    closed = sorted(
        [t for t in exe.get_all_trades() if t.status == "closed"],
        key=lambda t: t.closed_at,
        reverse=True,
    )
    streak = 0
    for t in closed:
        if t.pnl > 0:
            streak += 1
        else:
            break
    return streak


def _performance_score(win_rate: float, wins: int, total: int) -> int:
    if total == 0:
        return 0
    wr_pts       = min(win_rate / 100 * 500, 500)
    win_pts      = min(wins * 25, 300)
    activity_pts = min(total * 5, 200)
    return int(wr_pts + win_pts + activity_pts)
