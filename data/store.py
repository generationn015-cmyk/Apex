"""
Trade Store — SQLite persistence layer.
Saves all trades for performance tracking, backtesting, and audit.
"""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import aiosqlite

if TYPE_CHECKING:
    from execution.engine import ManagedTrade

log = logging.getLogger("apex.store")

CREATE_TRADES_TABLE = """
CREATE TABLE IF NOT EXISTS trades (
    trade_id TEXT PRIMARY KEY,
    strategy TEXT,
    pair TEXT,
    venue TEXT,
    direction TEXT,
    confidence REAL,
    entry_price REAL,
    stop_price REAL,
    target_price REAL,
    fill_price REAL,
    exit_price REAL,
    size REAL,
    leverage INTEGER,
    pnl REAL,
    status TEXT,
    close_reason TEXT,
    opened_at REAL,
    closed_at REAL,
    metadata TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
"""

CREATE_SIGNALS_TABLE = """
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy TEXT,
    pair TEXT,
    venue TEXT,
    direction TEXT,
    confidence REAL,
    entry_price REAL,
    stop_price REAL,
    target_price REAL,
    executed INTEGER DEFAULT 0,
    reject_reason TEXT,
    ts REAL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
"""

CREATE_BALANCE_TABLE = """
CREATE TABLE IF NOT EXISTS balance_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venue TEXT,
    balance REAL,
    ts REAL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
"""


class TradeStore:
    def __init__(self, db_path: str = "data/apex.db"):
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        import os
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        self._db = await aiosqlite.connect(self.db_path)
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute(CREATE_TRADES_TABLE)
        await self._db.execute(CREATE_SIGNALS_TABLE)
        await self._db.execute(CREATE_BALANCE_TABLE)
        await self._db.commit()
        log.info("TradeStore connected: %s", self.db_path)

    async def disconnect(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    async def save_trade(self, trade: "ManagedTrade") -> None:
        if not self._db:
            return
        try:
            await self._db.execute("""
                INSERT OR REPLACE INTO trades
                (trade_id, strategy, pair, venue, direction, confidence,
                 entry_price, stop_price, target_price, fill_price, exit_price,
                 size, pnl, status, close_reason, opened_at, closed_at, metadata)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                trade.trade_id,
                trade.signal.strategy,
                trade.signal.pair,
                trade.signal.venue,
                trade.signal.direction.value,
                trade.signal.confidence,
                trade.signal.entry_price,
                trade.signal.stop_price,
                trade.signal.target_price,
                trade.entry_fill_price,
                0.0,
                trade.entry_order.filled_size,
                trade.pnl,
                trade.status,
                trade.close_reason,
                trade.opened_at,
                trade.closed_at,
                json.dumps(trade.signal.metadata),
            ))
            await self._db.commit()
        except Exception as e:
            log.error("save_trade: %s", e)

    async def update_trade(self, trade: "ManagedTrade") -> None:
        if not self._db:
            return
        try:
            await self._db.execute("""
                UPDATE trades SET
                    exit_price=?, pnl=?, status=?, close_reason=?, closed_at=?
                WHERE trade_id=?
            """, (
                trade.entry_fill_price if trade.close_reason == "" else
                    (trade.signal.stop_price if trade.close_reason == "STOP_HIT" else trade.signal.target_price),
                trade.pnl,
                trade.status,
                trade.close_reason,
                trade.closed_at,
                trade.trade_id,
            ))
            await self._db.commit()
        except Exception as e:
            log.error("update_trade: %s", e)

    async def log_signal(self, signal, executed: bool, reject_reason: str = "") -> None:
        if not self._db:
            return
        import time
        try:
            await self._db.execute("""
                INSERT INTO signals
                (strategy, pair, venue, direction, confidence, entry_price,
                 stop_price, target_price, executed, reject_reason, ts)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (
                signal.strategy, signal.pair, signal.venue,
                signal.direction.value, signal.confidence,
                signal.entry_price, signal.stop_price, signal.target_price,
                1 if executed else 0, reject_reason, time.time(),
            ))
            await self._db.commit()
        except Exception as e:
            log.error("log_signal: %s", e)

    async def log_balance(self, venue: str, balance: float) -> None:
        if not self._db:
            return
        import time
        try:
            await self._db.execute(
                "INSERT INTO balance_history (venue, balance, ts) VALUES (?,?,?)",
                (venue, balance, time.time())
            )
            await self._db.commit()
        except Exception as e:
            log.error("log_balance: %s", e)

    async def get_recent_trades(self, limit: int = 50) -> list[dict]:
        if not self._db:
            return []
        async with self._db.execute(
            "SELECT * FROM trades ORDER BY opened_at DESC LIMIT ?", (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
            cols = [d[0] for d in cursor.description]
            return [dict(zip(cols, row)) for row in rows]

    async def get_performance_stats(self) -> dict:
        if not self._db:
            return {}
        async with self._db.execute("""
            SELECT
                COUNT(*) as total_trades,
                SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                SUM(pnl) as total_pnl,
                AVG(pnl) as avg_pnl,
                MAX(pnl) as best_trade,
                MIN(pnl) as worst_trade
            FROM trades WHERE status='closed'
        """) as cursor:
            row = await cursor.fetchone()
            if not row:
                return {}
            cols = [d[0] for d in cursor.description]
            stats = dict(zip(cols, row))
            if stats["total_trades"] and stats["total_trades"] > 0:
                stats["win_rate"] = round(stats["wins"] / stats["total_trades"] * 100, 1)
            return stats
