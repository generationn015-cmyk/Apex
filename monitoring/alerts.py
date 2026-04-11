"""
Telegram Alert System
Sends real-time trade notifications to your Telegram chat.
Setup: Create a bot via @BotFather, get your chat_id via @userinfobot
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import aiohttp

if TYPE_CHECKING:
    from execution.engine import ManagedTrade
    from strategies.base import Signal

log = logging.getLogger("apex.alerts")


class TelegramAlerter:
    def __init__(self, config: dict):
        tg = config.get("monitoring", {}).get("telegram", {})
        self.enabled: bool = tg.get("enabled", False)
        self.bot_token: str = tg.get("bot_token", "")
        self.chat_id: str = tg.get("chat_id", "")
        self.alert_on_trade: bool = tg.get("alert_on_trade", True)
        self.alert_on_stop: bool = tg.get("alert_on_stop_hit", True)
        self.alert_on_halt: bool = tg.get("alert_on_daily_loss_limit", True)
        self._session: aiohttp.ClientSession | None = None

    async def connect(self) -> None:
        if self.enabled and self.bot_token:
            self._session = aiohttp.ClientSession()
            log.info("Telegram alerter connected")

    async def disconnect(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    async def trade_opened(self, trade: "ManagedTrade") -> None:
        if not self.alert_on_trade:
            return
        s = trade.signal
        arrow = "" if "long" in s.direction.value else ""
        msg = (
            f"*APEX — TRADE OPEN* {arrow}\n"
            f"`{trade.trade_id}`\n\n"
            f"Pair: *{s.pair}* on {s.venue.upper()}\n"
            f"Direction: *{s.direction.value.upper()}*\n"
            f"Strategy: {s.strategy}\n"
            f"Confidence: {s.confidence:.0%}\n\n"
            f"Entry: `{s.entry_price:.4f}`\n"
            f"Stop:  `{s.stop_price:.4f}` (-{s.stop_pct:.2f}%)\n"
            f"Target: `{s.target_price:.4f}` (+{s.target_pct:.2f}%)\n"
            f"R:R = {s.risk_reward:.1f}x"
        )
        await self._send(msg)

    async def trade_closed(self, trade: "ManagedTrade") -> None:
        if trade.close_reason == "STOP_HIT" and not self.alert_on_stop:
            return
        pnl = trade.pnl
        sign = "+" if pnl >= 0 else ""
        emoji = "" if pnl >= 0 else ""
        msg = (
            f"*APEX — TRADE CLOSED* {emoji}\n"
            f"`{trade.trade_id}`\n\n"
            f"Pair: *{trade.signal.pair}*\n"
            f"Reason: *{trade.close_reason}*\n"
            f"PNL: *{sign}${pnl:.4f}*\n"
            f"Duration: {int(trade.closed_at - trade.opened_at)}s"
        )
        await self._send(msg)

    async def daily_loss_halt(self, daily_loss_pct: float, balance: float) -> None:
        if not self.alert_on_halt:
            return
        msg = (
            f"*APEX — TRADING HALTED*\n\n"
            f"Daily loss limit reached: *{daily_loss_pct:.1f}%*\n"
            f"Current balance: *${balance:.2f}*\n\n"
            f"_Trading resumes at midnight UTC_"
        )
        await self._send(msg)

    async def daily_summary(self, stats: dict) -> None:
        wins = stats.get("win_count", 0)
        losses = stats.get("loss_count", 0)
        pnl = stats.get("realized_pnl", 0)
        balance = stats.get("balance", 0)
        sign = "+" if pnl >= 0 else ""
        emoji = "" if pnl >= 0 else ""
        msg = (
            f"*APEX — DAILY SUMMARY* {emoji}\n\n"
            f"Balance: *${balance:.2f}*\n"
            f"PNL: *{sign}${pnl:.4f}*\n"
            f"Trades: {wins + losses} ({wins}W / {losses}L)\n"
            f"Win Rate: {stats.get('win_rate', 0):.0%}\n"
            f"Drawdown: {stats.get('drawdown_pct', 0):.1f}%"
        )
        await self._send(msg)

    async def send_custom(self, message: str) -> None:
        await self._send(message)

    async def _send(self, text: str) -> None:
        if not self.enabled or not self._session or not self.bot_token:
            return
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        try:
            async with self._session.post(url, json={
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "Markdown",
            }) as resp:
                if resp.status != 200:
                    log.warning("Telegram send failed: %s", await resp.text())
        except Exception as e:
            log.debug("Telegram send error: %s", e)
