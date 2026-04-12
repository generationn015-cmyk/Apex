"""
APEX — Unified Telegram Command Bot
Two-way: slash commands + free-text routed through Claude AI.

Commands:
  /status   — all agents PnL + open positions
  /report   — full performance breakdown
  /balance  — account balance (paper or live)
  /pause    — stop trading
  /resume   — resume trading
  /flip_live — switch to live mode (requires confirmation)
  /ping     — health check

Free text → Claude AI sees full system state and responds intelligently.
"""
import asyncio
import json
import os
import subprocess
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from configs.config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, STATE_FILE, ANTHROPIC_API_KEY


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


# ── Claude AI free-text handler ───────────────────────────────────────────────

_APEX_ROOT = Path(__file__).parent.parent
_PAPER_LOG = _APEX_ROOT / "logs" / "paper_trades.jsonl"

def _build_context() -> str:
    """Build a compact system snapshot for Claude to reason about."""
    state = _load_state()
    lines = []

    if state:
        s = state.get("stats", {})
        lines.append(f"APEX STATE (cycle {state.get('cycle',0)}, mode={state.get('mode','?')}):")
        lines.append(f"  PnL=${s.get('total_pnl',0):.2f}  WR={s.get('win_rate',0)}%  trades={s.get('total_trades',0)}  open={s.get('open',0)}")
        sigs = state.get("last_signals", {})
        active = {a:v for a,v in sigs.items() if v}
        if active:
            lines.append(f"  Last signals: {json.dumps(active, default=str)[:400]}")

    # Last 5 trades
    try:
        if _PAPER_LOG.exists():
            rows = _PAPER_LOG.read_text().strip().split("\n")[-5:]
            trades = [json.loads(r) for r in rows if r]
            lines.append(f"Recent trades: {json.dumps(trades, default=str)[:600]}")
    except Exception:
        pass

    lines.append(f"Current UTC time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}")
    lines.append("Paused: " + str(is_paused()))
    return "\n".join(lines)


def claude_reply(user_text: str) -> str:
    """Send free-text to Claude with full system context. Returns reply."""
    if not ANTHROPIC_API_KEY:
        return (
            "⚠️ ANTHROPIC_API_KEY not set — free-text AI disabled.\n"
            "Add it to .env to enable natural language commands.\n"
            "Available: /status /report /balance /pause /resume /ping"
        )
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        context = _build_context()
        system = (
            "You are the APEX trading bot's AI assistant, responding via Telegram. "
            "You have full visibility into the bot's state shown below. "
            "Answer concisely (under 300 chars when possible). "
            "If the user asks you to DO something (pause, resume, change settings), "
            "tell them you've noted it and describe what they should do via /command, "
            "or tell them it's been done if it's a read-only action. "
            "Be direct, smart, and talk like a trading partner not a chatbot.\n\n"
            f"SYSTEM SNAPSHOT:\n{context}"
        )
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": user_text}],
            system=system,
        )
        return resp.content[0].text.strip()
    except Exception as e:
        return f"⚠️ AI error: {e}"


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
    _send(
        "🚀 <b>APEX Bot online.</b>\n"
        "Commands: /status /report /balance /pause /resume /ping\n"
        "Or just talk to me — I'll respond using AI."
    )

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

            # Match slash command (handle /cmd@BotName format)
            first_word = text.split()[0]
            if first_word.startswith("/"):
                cmd = first_word.split("@")[0].lower()
                handler = COMMANDS.get(cmd)
                if handler:
                    try:
                        reply = handler()
                    except Exception as e:
                        reply = f"⚠️ Error: {e}"
                else:
                    reply = (
                        f"Unknown: <code>{cmd}</code>\n"
                        "Try: /status /report /balance /pause /resume /ping"
                    )
            else:
                # Free-text → Claude AI
                reply = claude_reply(text)

            _send(reply)

        time.sleep(1)


if __name__ == "__main__":
    run_bot()
