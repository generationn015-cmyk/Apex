"""
APEX — Unified Telegram Command Bot
Replaces: brain_loop.py, final_loop.py, telegram_relay.py

Commands:
  /status   — all agents PnL + open positions
  /report   — full performance breakdown
  /balance  — account balance (paper or live)
  /pause    — stop trading
  /resume   — resume trading
  /flip_live — switch to live mode (requires confirmation)
  /stop_loss — show current open stop levels
  /ping     — health check
"""
import asyncio
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from configs.config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, STATE_FILE


# ── Pause flag (file-based so watchdog can read it) ──────────────────────────
PAUSE_FILE = Path(__file__).parent.parent / "logs" / ".paused"

def is_paused() -> bool:
    return PAUSE_FILE.exists()

def set_paused(paused: bool):
    if paused:
        PAUSE_FILE.touch()
    elif PAUSE_FILE.exists():
        PAUSE_FILE.unlink()


# ── Telegram helpers ─────────────────────────────────────────────────────────

def _send(text: str, chat_id: str = TELEGRAM_CHAT_ID):
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }).encode()
    try:
        urllib.request.urlopen(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data=data, timeout=10
        )
    except Exception as e:
        print(f"[Telegram] send failed: {e}")


def _get_updates(offset=None) -> list:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?timeout=20"
    if offset:
        url += f"&offset={offset}"
    try:
        with urllib.request.urlopen(url, timeout=25) as f:
            return json.loads(f.read().decode()).get("result", [])
    except Exception:
        return []


# ── State reader ─────────────────────────────────────────────────────────────

def _load_state() -> dict:
    try:
        if STATE_FILE.exists():
            with open(STATE_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


# ── Command handlers ─────────────────────────────────────────────────────────

def cmd_status() -> str:
    state = _load_state()
    if not state:
        return "⚠️ No state file yet — bot may not have run a cycle"

    mode  = state.get("mode", "unknown").upper()
    cycle = state.get("cycle", 0)
    stats = state.get("stats", {})
    updated = state.get("updated_at", "")[:19].replace("T", " ")

    paused_tag = " ⏸ PAUSED" if is_paused() else ""
    lines = [
        f"<b>APEX STATUS{paused_tag}</b>",
        f"Mode: {mode}  |  Cycle: {cycle}  |  Updated: {updated} UTC",
        "",
        f"📊 <b>Performance</b>",
        f"  Trades: {stats.get('total_trades', 0)} "
        f"({stats.get('open', 0)} open / {stats.get('closed', 0)} closed)",
        f"  Win Rate: {stats.get('win_rate', 0)}%",
        f"  Net PnL:  ${stats.get('total_pnl', 0):.2f}",
        f"  Wins: {stats.get('wins', 0)}  Losses: {stats.get('losses', 0)}",
    ]

    # Per-agent breakdown
    last_signals = state.get("last_signals", {})
    if last_signals:
        lines.append("\n📡 <b>Last Signals</b>")
        for agent, sigs in last_signals.items():
            if sigs:
                for s in sigs:
                    lines.append(
                        f"  {agent} | {s['asset']} | {s['signal']} "
                        f"@ {s['entry_price']:.4f} (str={s['strength']:.2f})"
                    )

    return "\n".join(lines)


def cmd_report() -> str:
    state = _load_state()
    if not state:
        return "No data yet."
    stats = state.get("stats", {})
    lines = [
        "<b>APEX FULL REPORT</b>",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        f"Total trades:  {stats.get('total_trades', 0)}",
        f"Open:          {stats.get('open', 0)}",
        f"Closed:        {stats.get('closed', 0)}",
        f"Wins:          {stats.get('wins', 0)}",
        f"Losses:        {stats.get('losses', 0)}",
        f"Win rate:      {stats.get('win_rate', 0)}%",
        f"Net PnL:       ${stats.get('total_pnl', 0):.2f}",
        f"Max drawdown:  {stats.get('max_drawdown', 0):.2f}%",
    ]
    return "\n".join(lines)


def cmd_pause() -> str:
    set_paused(True)
    return "⏸ Trading PAUSED. Send /resume to restart."


def cmd_resume() -> str:
    set_paused(False)
    return "▶️ Trading RESUMED."


def cmd_balance() -> str:
    state = _load_state()
    mode = state.get("mode", "paper")
    if mode == "paper":
        stats = state.get("stats", {})
        pnl   = stats.get("total_pnl", 0)
        return f"💰 Paper balance PnL: ${pnl:.2f}"
    return "💰 Live balance — connect to Lighter.xyz for real balance"


def cmd_flip_live() -> str:
    from configs.config import LIGHTER_API_KEY_ID
    if not LIGHTER_API_KEY_ID:
        return (
            "❌ Cannot flip to live: LIGHTER_API_KEY_ID not set.\n"
            "Get your API key at app.lighter.xyz → API Keys, "
            "add to .env, then restart with --live flag."
        )
    return (
        "⚠️ <b>LIVE MODE WARNING</b>\n"
        "This will use real money on Lighter.xyz (zero-fee perps).\n"
        "To confirm: restart bot with <code>python3 main.py --live</code>"
    )


def cmd_ping() -> str:
    state = _load_state()
    updated = state.get("updated_at", "never")[:19].replace("T", " ") if state else "never"
    paused  = " (PAUSED)" if is_paused() else ""
    return f"🏓 PONG — last cycle: {updated} UTC{paused}"


COMMANDS = {
    "/status":    cmd_status,
    "/report":    cmd_report,
    "/pause":     cmd_pause,
    "/resume":    cmd_resume,
    "/balance":   cmd_balance,
    "/flip_live": cmd_flip_live,
    "/ping":      cmd_ping,
    "ping":       cmd_ping,
}


# ── Heartbeat helper (called from main.py) ────────────────────────────────────

async def send_heartbeat(report: dict):
    stats = report.get("global", {})
    msg = (
        f"💓 <b>APEX Heartbeat</b>\n"
        f"Cycle {report.get('cycle', 0)}  |  "
        f"WR: {stats.get('win_rate', 0)}%  |  "
        f"PnL: ${stats.get('total_pnl', 0):.2f}"
    )
    _send(msg)


# ── Main polling loop ─────────────────────────────────────────────────────────

def run_bot():
    _send("🚀 <b>APEX Bot online.</b>\nCommands: /status /report /balance /pause /resume /ping")

    last_id = None
    while True:
        updates = _get_updates(last_id)
        for update in updates:
            last_id = update["update_id"] + 1
            msg = update.get("message", {})
            if str(msg.get("chat", {}).get("id")) != str(TELEGRAM_CHAT_ID):
                continue

            text = msg.get("text", "").strip()
            if not text:
                continue

            # Match command (handle /cmd@BotName format)
            cmd = text.split()[0].split("@")[0].lower()
            handler = COMMANDS.get(cmd)
            if handler:
                try:
                    reply = handler()
                except Exception as e:
                    reply = f"⚠️ Error: {e}"
            else:
                reply = (
                    f"Unknown command: <code>{cmd}</code>\n"
                    "Try: /status /report /balance /pause /resume /ping"
                )

            _send(reply)

        time.sleep(1)


if __name__ == "__main__":
    run_bot()
