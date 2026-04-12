"""
APEX -- Unified Telegram Command Bot
One clean consolidated notification instead of spam.
Two-way: slash commands + free-text routed through Claude AI.

Commands:
  /status   -- all systems status + PnL
  /report   -- full performance breakdown
  /balance  -- account balance (paper or live)
  /pause    -- stop trading
  /resume   -- resume trading
  /flip_live -- switch to live mode (requires confirmation)
  /ping     -- health check
"""
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from configs.config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, STATE_FILE, ANTHROPIC_API_KEY


# -- Pause flag (file-based so watchdog can read it) ---------------------------
PAUSE_FILE = Path(__file__).parent.parent / "logs" / ".paused"
POLY_DATA = Path(__file__).parent.parent / "polymarket" / "data"
NOTIFICATION_QUEUE = POLY_DATA / "notification_queue.jsonl"
LAST_DIGEST_FILE = Path(__file__).parent.parent / "logs" / ".last_digest"
DIGEST_INTERVAL = 3600  # 1 hour between consolidated digests


def is_paused() -> bool:
    return PAUSE_FILE.exists()

def set_paused(paused: bool):
    if paused:
        PAUSE_FILE.touch()
    elif PAUSE_FILE.exists():
        PAUSE_FILE.unlink()


# -- Telegram helpers ----------------------------------------------------------

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


# -- State readers -------------------------------------------------------------

def _load_state() -> dict:
    try:
        if STATE_FILE.exists():
            with open(STATE_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _load_json(p: Path) -> dict | None:
    try:
        if p.exists():
            return json.loads(p.read_text())
    except Exception:
        pass
    return None


def _drain_notification_queue() -> list[dict]:
    """Read and clear the notification queue from subsystems."""
    entries = []
    try:
        if NOTIFICATION_QUEUE.exists():
            for line in NOTIFICATION_QUEUE.read_text().splitlines():
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except Exception:
                        pass
            # Clear the queue after reading
            NOTIFICATION_QUEUE.write_text("")
    except Exception:
        pass
    return entries


# -- Consolidated Digest -------------------------------------------------------

def _build_digest() -> str | None:
    """
    Build ONE clean consolidated status message from all subsystems.
    Returns None if nothing meaningful to report.
    """
    lines = ["<b>APEX Status Update</b>"]
    has_content = False

    # -- Crypto Agents ---------------------------------------------------------
    state = _load_state()
    if state:
        s = state.get("stats", {})
        mode = state.get("mode", "paper").upper()
        cycle = state.get("cycle", 0)
        pnl = s.get("total_pnl", 0)
        wr = s.get("win_rate", 0)
        trades = s.get("total_trades", 0)
        pnl_sign = "+" if pnl >= 0 else ""
        lines.append(
            f"\n<b>Crypto Agents</b> ({mode} C{cycle})"
            f"\n  PnL: {pnl_sign}${pnl:.2f} | WR: {wr}% | Trades: {trades}"
        )
        has_content = True

    # -- BTC 5-Min Sniper ------------------------------------------------------
    btc_state = _load_json(POLY_DATA / "btc_5m_state.json")
    if btc_state:
        bankroll = btc_state.get("bankroll", 0)
        btc_trades = btc_state.get("trades", [])
        resolved = [t for t in btc_trades if t.get("resolved")]
        wins = sum(1 for t in resolved if t.get("won"))
        total = len(resolved)
        btc_pnl = sum(t.get("pnl", 0) for t in resolved)
        wr = round(wins / total * 100) if total else 0
        scanned = btc_state.get("windows_scanned", 0)
        pnl_sign = "+" if btc_pnl >= 0 else ""
        lines.append(
            f"\n<b>BTC 5-Min Sniper</b>"
            f"\n  Bank: ${bankroll:.2f} | PnL: {pnl_sign}${btc_pnl:.2f}"
            f"\n  {wins}W/{total-wins}L ({wr}%) | Scanned: {scanned}"
        )

        # Last trade result
        if resolved:
            last = resolved[-1]
            emoji = "W" if last.get("won") else "L"
            last_pnl = last.get("pnl", 0)
            lines.append(
                f"  Last: {last.get('direction', '?')} {emoji} "
                f"${last_pnl:+.2f} @ {last.get('confidence', 0):.0%} conf"
            )
        has_content = True

    # -- Polymarket Scanner ----------------------------------------------------
    sniper = _load_json(POLY_DATA / "sniper_state.json")
    if sniper:
        open_count = len(sniper.get("positions", {}))
        hist = sniper.get("history", [])
        s_pnl = sum(h.get("pnl", 0) for h in hist if h.get("result"))
        if open_count or hist:
            pnl_sign = "+" if s_pnl >= 0 else ""
            lines.append(
                f"\n<b>Poly Scanner</b>"
                f"\n  Open: {open_count} | PnL: {pnl_sign}${s_pnl:.2f}"
            )
            has_content = True

    # -- Copy Trader -----------------------------------------------------------
    copy_status = _load_json(POLY_DATA / "copy_trader_status.json")
    if copy_status:
        c_bank = copy_status.get("bankroll", 0)
        c_hist = copy_status.get("history", [])
        c_open = len(copy_status.get("positions", {}))
        c_pnl = sum(h.get("pnl", 0) for h in c_hist if h.get("resolved"))
        wallets = copy_status.get("total_wallets_tracked", 0)
        if c_open or c_hist or wallets:
            pnl_sign = "+" if c_pnl >= 0 else ""
            lines.append(
                f"\n<b>Copy Trader</b>"
                f"\n  Bank: ${c_bank:.2f} | Open: {c_open} | PnL: {pnl_sign}${c_pnl:.2f}"
                f"\n  Wallets: {wallets}"
            )
            has_content = True

    # -- Queued notifications (summarize, don't replay each one) ---------------
    queued = _drain_notification_queue()
    if queued:
        btc_events = [q for q in queued if q.get("source") == "btc_5m_sniper"]
        poly_events = [q for q in queued if q.get("source") == "polymarket_sniper"]
        copy_events = [q for q in queued if q.get("source") == "copy_trader"]

        event_parts = []
        if btc_events:
            event_parts.append(f"{len(btc_events)} BTC sniper")
        if poly_events:
            event_parts.append(f"{len(poly_events)} scanner")
        if copy_events:
            event_parts.append(f"{len(copy_events)} copy")

        if event_parts:
            lines.append(f"\nEvents: {', '.join(event_parts)}")
            has_content = True

    # -- Footer ----------------------------------------------------------------
    paused = " | PAUSED" if is_paused() else ""
    now = datetime.now(timezone.utc).strftime("%H:%M UTC")
    lines.append(f"\n<i>{now}{paused}</i>")

    if not has_content:
        return None
    return "\n".join(lines)


def _should_send_digest() -> bool:
    """Check if enough time has passed since last digest."""
    try:
        if LAST_DIGEST_FILE.exists():
            ts = float(LAST_DIGEST_FILE.read_text().strip())
            return (time.time() - ts) >= DIGEST_INTERVAL
    except Exception:
        pass
    return True


def _mark_digest_sent():
    try:
        LAST_DIGEST_FILE.write_text(str(time.time()))
    except Exception:
        pass


# -- Command handlers ----------------------------------------------------------

def cmd_status() -> str:
    digest = _build_digest()
    return digest or "No system data available yet."


def cmd_report() -> str:
    state = _load_state()
    btc_state = _load_json(POLY_DATA / "btc_5m_state.json")

    lines = [f"<b>APEX Full Report</b>"]
    lines.append(f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")

    if state:
        stats = state.get("stats", {})
        lines.append(f"\n<b>Crypto Agents</b>")
        lines.append(f"  Trades: {stats.get('total_trades', 0)}")
        lines.append(f"  Open: {stats.get('open', 0)} | Closed: {stats.get('closed', 0)}")
        lines.append(f"  Wins: {stats.get('wins', 0)} | Losses: {stats.get('losses', 0)}")
        lines.append(f"  Win rate: {stats.get('win_rate', 0)}%")
        lines.append(f"  Net PnL: ${stats.get('total_pnl', 0):.2f}")

    if btc_state:
        trades = btc_state.get("trades", [])
        resolved = [t for t in trades if t.get("resolved")]
        wins = sum(1 for t in resolved if t.get("won"))
        total = len(resolved)
        pnl = sum(t.get("pnl", 0) for t in resolved)
        lines.append(f"\n<b>BTC 5-Min Sniper</b>")
        lines.append(f"  Bankroll: ${btc_state.get('bankroll', 0):.2f}")
        lines.append(f"  Trades: {total} ({wins}W / {total - wins}L)")
        lines.append(f"  Win rate: {round(wins/total*100) if total else 0}%")
        lines.append(f"  Net PnL: ${pnl:+.2f}")
        lines.append(f"  Windows scanned: {btc_state.get('windows_scanned', 0)}")

    return "\n".join(lines)


def cmd_pause() -> str:
    set_paused(True)
    return "Trading PAUSED. /resume to restart."


def cmd_resume() -> str:
    set_paused(False)
    return "Trading RESUMED."


def cmd_balance() -> str:
    state = _load_state()
    btc = _load_json(POLY_DATA / "btc_5m_state.json")

    lines = []
    if state:
        pnl = state.get("stats", {}).get("total_pnl", 0)
        lines.append(f"Crypto PnL: ${pnl:+.2f}")
    if btc:
        lines.append(f"BTC Sniper: ${btc.get('bankroll', 0):.2f}")

    return "\n".join(lines) if lines else "No balance data."


def cmd_flip_live() -> str:
    from configs.config import LIGHTER_API_KEY_ID
    if not LIGHTER_API_KEY_ID:
        return (
            "Cannot flip to live: LIGHTER_API_KEY_ID not set.\n"
            "Get your API key at app.lighter.xyz, add to .env, restart with --live."
        )
    return (
        "<b>LIVE MODE WARNING</b>\n"
        "Real money on Lighter.xyz.\n"
        "Confirm: restart with <code>python3 main.py --live</code>"
    )


def cmd_ping() -> str:
    state = _load_state()
    updated = state.get("updated_at", "never")[:19].replace("T", " ") if state else "never"
    paused = " (PAUSED)" if is_paused() else ""
    return f"PONG -- last cycle: {updated} UTC{paused}"


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


# -- Claude AI free-text handler -----------------------------------------------

_APEX_ROOT = Path(__file__).parent.parent
_PAPER_LOG = _APEX_ROOT / "logs" / "paper_trades.jsonl"

def _build_context() -> str:
    state = _load_state()
    btc = _load_json(POLY_DATA / "btc_5m_state.json")
    lines = []

    if state:
        s = state.get("stats", {})
        lines.append(f"APEX (cycle {state.get('cycle',0)}, mode={state.get('mode','?')}):")
        lines.append(f"  PnL=${s.get('total_pnl',0):.2f}  WR={s.get('win_rate',0)}%  trades={s.get('total_trades',0)}")
        sigs = state.get("last_signals", {})
        active = {a: v for a, v in sigs.items() if v}
        if active:
            lines.append(f"  Signals: {json.dumps(active, default=str)[:400]}")

    if btc:
        resolved = [t for t in btc.get("trades", []) if t.get("resolved")]
        wins = sum(1 for t in resolved if t.get("won"))
        pnl = sum(t.get("pnl", 0) for t in resolved)
        lines.append(f"BTC Sniper: bank=${btc.get('bankroll',0):.2f} pnl=${pnl:+.2f} {wins}W/{len(resolved)}T")

    try:
        if _PAPER_LOG.exists():
            rows = _PAPER_LOG.read_text().strip().split("\n")[-5:]
            trades = [json.loads(r) for r in rows if r]
            lines.append(f"Recent: {json.dumps(trades, default=str)[:400]}")
    except Exception:
        pass

    lines.append(f"UTC: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"Paused: {is_paused()}")
    return "\n".join(lines)


def _try_execute_action(intent: str) -> str | None:
    import re
    m = re.search(r'\[ACTION:(\w+)\]', intent)
    if not m:
        return None
    action = m.group(1).lower()
    handlers = {
        "pause": cmd_pause, "resume": cmd_resume, "status": cmd_status,
        "report": cmd_report, "balance": cmd_balance, "ping": cmd_ping,
    }
    fn = handlers.get(action)
    if fn:
        try:
            return fn()
        except Exception as e:
            return f"Action {action} failed: {e}"
    return None


def claude_reply(user_text: str) -> str:
    if not ANTHROPIC_API_KEY:
        return "AI offline. Commands: /status /report /balance /pause /resume /ping"
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        context = _build_context()
        system = (
            "You are the APEX trading bot AI on Telegram.\n"
            "Rules: concise (max 3 sentences), sharp, no made-up data.\n"
            "Embed [ACTION:pause] etc. to trigger commands.\n\n"
            f"SNAPSHOT:\n{context}"
        )
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": user_text}],
            system=system,
        )
        raw = resp.content[0].text.strip()
        action_result = _try_execute_action(raw)
        import re
        display = re.sub(r'\[ACTION:\w+\]', '', raw).strip()
        if action_result:
            return f"{display}\n\n{action_result}"
        return display
    except Exception as e:
        return f"AI error: {e}"


# -- Heartbeat helper (called from main.py) ------------------------------------

async def send_heartbeat(report: dict):
    """Heartbeat is now handled by the consolidated digest. No-op for backwards compat."""
    pass


# -- Main polling loop ---------------------------------------------------------

def run_bot():
    _send("APEX Bot online. /status for overview.")

    last_id = None
    while True:
        # -- Handle incoming commands ------------------------------------------
        updates = _get_updates(last_id)
        for update in updates:
            last_id = update["update_id"] + 1
            msg = update.get("message", {})
            if str(msg.get("chat", {}).get("id")) != str(TELEGRAM_CHAT_ID):
                continue

            text = msg.get("text", "").strip()
            if not text:
                continue

            first_word = text.split()[0]
            if first_word.startswith("/"):
                cmd = first_word.split("@")[0].lower()
                handler = COMMANDS.get(cmd)
                if handler:
                    try:
                        reply = handler()
                    except Exception as e:
                        reply = f"Error: {e}"
                else:
                    reply = f"Unknown: {cmd}\n/status /report /balance /pause /resume /ping"
            else:
                reply = claude_reply(text)

            _send(reply)

        # -- Periodic consolidated digest --------------------------------------
        if _should_send_digest():
            digest = _build_digest()
            if digest:
                _send(digest)
            _mark_digest_sent()

        time.sleep(1)


if __name__ == "__main__":
    run_bot()
