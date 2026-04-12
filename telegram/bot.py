"""
APEX — Telegram Bot
════════════════════
ONE hourly digest. Clean commands. No spam.

Commands:
  /status    — full system overview
  /btc       — BTC 5-min sniper performance
  /agents    — crypto agent breakdown
  /poly      — polymarket scanner positions
  /copy      — copy trader status
  /balance   — all bankrolls
  /report    — detailed performance report
  /pause     — pause all trading
  /resume    — resume trading
  /live      — switch to live mode
  /ping      — health check
  /help      — list all commands
"""
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from configs.config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, STATE_FILE, ANTHROPIC_API_KEY

_ROOT = Path(__file__).parent.parent
_LOGS = _ROOT / "logs"
_POLY = _ROOT / "polymarket" / "data"
_PAUSE_FILE = _LOGS / ".paused"
_DIGEST_FILE = _LOGS / ".last_digest"
_DIGEST_INTERVAL = 3600  # 1 hour


# ── Telegram I/O ─────────────────────────────────────────────────────────────

def _send(text: str, chat_id: str = TELEGRAM_CHAT_ID):
    data = urllib.parse.urlencode({
        "chat_id": chat_id, "text": text, "parse_mode": "HTML",
    }).encode()
    try:
        urllib.request.urlopen(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data=data, timeout=10,
        )
    except Exception as e:
        print(f"[TG] send failed: {e}")


def _poll(offset=None) -> list:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?timeout=20"
    if offset:
        url += f"&offset={offset}"
    try:
        with urllib.request.urlopen(url, timeout=25) as f:
            return json.loads(f.read().decode()).get("result", [])
    except Exception:
        return []


# ── Data Loaders ─────────────────────────────────────────────────────────────

def _json(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text()) if p.exists() else None
    except Exception:
        return None


def _is_paused() -> bool:
    return _PAUSE_FILE.exists()


# ── Commands ─────────────────────────────────────────────────────────────────

def cmd_status() -> str:
    lines = ["<b>APEX System Status</b>"]
    paused = " [PAUSED]" if _is_paused() else ""
    lines[0] += paused

    # Processes
    wdog = _json(_LOGS / "watchdog_status.json")
    if wdog:
        procs = wdog.get("processes", {})
        for name, info in procs.items():
            st = info.get("status", "?")
            dot = "●" if st == "running" else "○"
            lines.append(f"  {dot} {name}: {st}")

    # Bankrolls
    btc = _json(_POLY / "btc_5m_state.json")
    copy = _json(_POLY / "copy_trader_status.json")
    state = _json(STATE_FILE)

    if btc:
        trades = btc.get("trades", [])
        resolved = [t for t in trades if t.get("resolved")]
        wins = sum(1 for t in resolved if t.get("won"))
        pnl = sum(t.get("pnl", 0) for t in resolved)
        lines.append(f"\n<b>BTC Sniper</b>: ${btc['bankroll']:.2f}")
        lines.append(f"  {wins}W/{len(resolved)-wins}L | PnL: ${pnl:+.2f}")

    if state:
        s = state.get("stats", {})
        lines.append(f"\n<b>Crypto Agents</b>: C{state.get('cycle',0)}")
        lines.append(f"  {s.get('wins',0)}W/{s.get('losses',0)}L | PnL: ${s.get('total_pnl',0):+.2f}")

    if copy:
        cp = copy.get("positions", {})
        lines.append(f"\n<b>Copy Trader</b>: ${copy.get('bankroll',0):.2f}")
        lines.append(f"  {len(cp)} open | {copy.get('total_wallets_tracked',0)} wallets")

    lines.append(f"\n{datetime.now(timezone.utc).strftime('%H:%M UTC')}")
    return "\n".join(lines)


def cmd_btc() -> str:
    btc = _json(_POLY / "btc_5m_state.json")
    if not btc:
        return "No BTC sniper data."
    trades = btc.get("trades", [])
    resolved = [t for t in trades if t.get("resolved")]
    wins = sum(1 for t in resolved if t.get("won"))
    pnl = sum(t.get("pnl", 0) for t in resolved)
    lines = [
        f"<b>BTC 5-Min Sniper</b>",
        f"Bankroll: ${btc['bankroll']:.2f}",
        f"Record: {wins}W / {len(resolved)-wins}L",
        f"PnL: ${pnl:+.2f}",
        f"Scanned: {btc.get('windows_scanned',0)} windows",
    ]
    # Last 3 trades
    for t in reversed(resolved[-3:]):
        emoji = "W" if t.get("won") else "L"
        lines.append(f"  {t['direction']} {emoji} ${t.get('pnl',0):+.2f} | {t.get('edge',0)*100:.1f}% edge")
    return "\n".join(lines)


def cmd_agents() -> str:
    state = _json(STATE_FILE)
    if not state:
        return "No agent data."
    s = state.get("stats", {})
    sigs = state.get("last_signals", {})
    lines = [
        f"<b>Crypto Agents</b> (C{state.get('cycle',0)} {state.get('mode','?').upper()})",
        f"Trades: {s.get('total_trades',0)} ({s.get('open',0)} open)",
        f"Record: {s.get('wins',0)}W / {s.get('losses',0)}L",
        f"PnL: ${s.get('total_pnl',0):+.2f}",
    ]
    for agent, signals in sigs.items():
        if signals:
            for sig in signals[:1]:
                d = "▲" if sig['signal'] == 'BUY' else "▼"
                lines.append(f"\n{agent}: {d} {sig['signal']} {sig['asset']}")
                lines.append(f"  str={sig['strength']:.2f} @ ${sig['entry_price']:,.2f}")
        else:
            lines.append(f"\n{agent}: watching")
    return "\n".join(lines)


def cmd_poly() -> str:
    sniper = _json(_POLY / "sniper_state.json")
    scan = _json(_POLY / "scan_results.json")
    lines = ["<b>Polymarket Scanner</b>"]

    if sniper:
        pos = sniper.get("positions", {})
        lines.append(f"Open: {len(pos)} | Bankroll: ${sniper.get('bankroll',0):.2f}")
        for cid, p in list(pos.items())[:3]:
            lines.append(f"  {p['direction']} {p['question'][:40]}...")

    if scan and isinstance(scan, list):
        top = [s for s in scan if s.get('edge', 0) > 0.01][:5]
        if top:
            lines.append(f"\nTop edges ({len(scan)} scanned):")
            for s in top:
                lines.append(f"  {s['edge']*100:.1f}% | {s['question'][:40]}")

    return "\n".join(lines) if len(lines) > 1 else "No scanner data."


def cmd_copy() -> str:
    copy = _json(_POLY / "copy_trader_status.json")
    if not copy:
        return "Copy trader not running."
    pos = copy.get("positions", {})
    lines = [
        f"<b>Copy Trader</b>",
        f"Bankroll: ${copy.get('bankroll',0):.2f}",
        f"Open: {len(pos)} positions",
        f"Wallets: {copy.get('total_wallets_tracked',0)} tracked",
    ]
    for cid, p in list(pos.items())[:5]:
        name = p.get("whale_name", p.get("whale_address", "")[:10])
        lines.append(f"  {p['side']} ${p['bet_size']:.2f} | {p.get('title','')[:30]} | {name}")
    return "\n".join(lines)


def cmd_balance() -> str:
    btc = _json(_POLY / "btc_5m_state.json")
    copy = _json(_POLY / "copy_trader_status.json")
    sniper = _json(_POLY / "sniper_state.json")
    state = _json(STATE_FILE)
    lines = ["<b>Bankrolls</b>"]
    if btc:
        lines.append(f"BTC Sniper: ${btc['bankroll']:.2f}")
    if copy:
        lines.append(f"Copy Trader: ${copy.get('bankroll',0):.2f}")
    if sniper:
        lines.append(f"Poly Scanner: ${sniper.get('bankroll',0):.2f}")
    if state:
        pnl = state.get("stats", {}).get("total_pnl", 0)
        lines.append(f"Crypto Agents PnL: ${pnl:+.2f}")
    return "\n".join(lines)


def cmd_report() -> str:
    btc = _json(_POLY / "btc_5m_state.json")
    state = _json(STATE_FILE)
    copy = _json(_POLY / "copy_trader_status.json")
    lines = [f"<b>APEX Performance Report</b>",
             f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"]

    if btc:
        trades = btc.get("trades", [])
        resolved = [t for t in trades if t.get("resolved")]
        wins = sum(1 for t in resolved if t.get("won"))
        pnl = sum(t.get("pnl", 0) for t in resolved)
        lines.append(f"\nBTC Sniper: ${btc['bankroll']:.2f}")
        lines.append(f"  {wins}W/{len(resolved)-wins}L | ${pnl:+.2f}")
        for t in resolved:
            w = "W" if t.get("won") else "L"
            lines.append(f"  {t['direction']} {w} ${t.get('pnl',0):+.2f}")

    if state:
        s = state.get("stats", {})
        lines.append(f"\nCrypto: {s.get('total_trades',0)} trades | ${s.get('total_pnl',0):+.2f}")

    if copy:
        h = copy.get("history", [])
        resolved = [x for x in h if x.get("resolved")]
        pnl = sum(x.get("pnl", 0) for x in resolved)
        lines.append(f"\nCopy: {len(copy.get('positions',{}))} open | ${pnl:+.2f}")

    return "\n".join(lines)


def cmd_pause() -> str:
    _PAUSE_FILE.touch()
    return "Trading PAUSED. /resume to restart."


def cmd_resume() -> str:
    if _PAUSE_FILE.exists():
        _PAUSE_FILE.unlink()
    return "Trading RESUMED."


def cmd_live() -> str:
    from configs.config import LIGHTER_API_KEY_ID
    if not LIGHTER_API_KEY_ID:
        return "Cannot go live: LIGHTER_API_KEY_ID not set."
    return "Restart with: python3 main.py --live"


def cmd_ping() -> str:
    state = _json(STATE_FILE)
    updated = state.get("updated_at", "?")[:19] if state else "?"
    p = " PAUSED" if _is_paused() else ""
    return f"PONG — {updated} UTC{p}"


def cmd_help() -> str:
    return (
        "<b>APEX Commands</b>\n"
        "/status  — system overview\n"
        "/btc     — BTC 5-min sniper\n"
        "/agents  — crypto agent breakdown\n"
        "/poly    — polymarket scanner\n"
        "/copy    — copy trader\n"
        "/balance — all bankrolls\n"
        "/report  — full performance\n"
        "/pause   — pause trading\n"
        "/resume  — resume trading\n"
        "/live    — switch to live\n"
        "/ping    — health check"
    )


COMMANDS = {
    "/status": cmd_status, "/btc": cmd_btc, "/agents": cmd_agents,
    "/poly": cmd_poly, "/copy": cmd_copy, "/balance": cmd_balance,
    "/report": cmd_report, "/pause": cmd_pause, "/resume": cmd_resume,
    "/live": cmd_live, "/ping": cmd_ping, "/help": cmd_help,
    "ping": cmd_ping,
}


# ── Hourly Digest ────────────────────────────────────────────────────────────

def _build_digest() -> str | None:
    """One clean message: bankroll + wins/losses. Nothing else."""
    btc = _json(_POLY / "btc_5m_state.json")
    state = _json(STATE_FILE)
    copy = _json(_POLY / "copy_trader_status.json")
    has_data = False
    lines = ["<b>APEX Hourly</b>"]

    if btc:
        trades = btc.get("trades", [])
        resolved = [t for t in trades if t.get("resolved")]
        wins = sum(1 for t in resolved if t.get("won"))
        pnl = sum(t.get("pnl", 0) for t in resolved)
        lines.append(f"BTC: ${btc['bankroll']:.2f} ({wins}W/{len(resolved)-wins}L ${pnl:+.2f})")
        has_data = True

    if state:
        s = state.get("stats", {})
        if s.get("total_trades", 0):
            lines.append(f"Agents: {s.get('wins',0)}W/{s.get('losses',0)}L ${s.get('total_pnl',0):+.2f}")
            has_data = True

    if copy and copy.get("positions"):
        lines.append(f"Copy: {len(copy['positions'])} open | {copy.get('total_wallets_tracked',0)} wallets")
        has_data = True

    if _is_paused():
        lines.append("⚠ PAUSED")

    lines.append(datetime.now(timezone.utc).strftime("%H:%M UTC"))
    return "\n".join(lines) if has_data else None


def _should_digest() -> bool:
    try:
        if _DIGEST_FILE.exists():
            return (time.time() - float(_DIGEST_FILE.read_text().strip())) >= _DIGEST_INTERVAL
    except Exception:
        pass
    return True


def _mark_digest():
    try:
        _DIGEST_FILE.write_text(str(time.time()))
    except Exception:
        pass


# ── Claude AI (optional) ────────────────────────────────────────────────────

def _ai_reply(text: str) -> str:
    if not ANTHROPIC_API_KEY:
        return "AI offline. /help for commands."
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        ctx = cmd_status()
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=300,
            system=f"You are APEX trading bot AI. Be concise (2-3 sentences). Data:\n{ctx}",
            messages=[{"role": "user", "content": text}],
        )
        return resp.content[0].text.strip()
    except Exception as e:
        return f"AI error: {e}"


# ── Heartbeat (backwards compat with main.py) ───────────────────────────────

async def send_heartbeat(report: dict):
    pass  # Handled by hourly digest


# ── Main Loop ────────────────────────────────────────────────────────────────

def run_bot():
    print("[TG] Bot started. No startup message sent.")
    last_id = None

    while True:
        updates = _poll(last_id)
        for update in updates:
            last_id = update["update_id"] + 1
            msg = update.get("message", {})
            if str(msg.get("chat", {}).get("id")) != str(TELEGRAM_CHAT_ID):
                continue

            text = msg.get("text", "").strip()
            if not text:
                continue

            first = text.split()[0]
            if first.startswith("/"):
                cmd = first.split("@")[0].lower()
                handler = COMMANDS.get(cmd)
                if handler:
                    try:
                        _send(handler())
                    except Exception as e:
                        _send(f"Error: {e}")
                else:
                    _send(f"Unknown: {cmd}\n/help for commands")
            else:
                _send(_ai_reply(text))

        # Hourly digest — only notification the user gets unprompted
        if _should_digest():
            digest = _build_digest()
            if digest:
                _send(digest)
            _mark_digest()

        time.sleep(1)


if __name__ == "__main__":
    run_bot()
