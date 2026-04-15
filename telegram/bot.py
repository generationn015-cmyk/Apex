"""
APEX — Telegram Bot
════════════════════
ONE hourly digest. Clean commands. No spam.

Commands:
  /status    — full system overview
  /btc       — BTC 5-min sniper stats
  /eth       — ETH 5-min sniper stats
  /balance   — all bankrolls
  /report    — detailed performance report
  /live      — switch to live mode
  /paper     — switch to paper mode
  /pause     — pause all trading
  /resume    — resume trading
  /ping      — health check
  /help      — list all commands
"""
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

DETROIT_TZ = ZoneInfo("America/Detroit")
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from configs.config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, STATE_FILE, ANTHROPIC_API_KEY

_ROOT = Path(__file__).parent.parent
_LOGS = _ROOT / "logs"
_POLY = _ROOT / "polymarket" / "data"
_PAUSE_FILE  = _LOGS / ".paused"
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


def _is_live() -> bool:
    return (_LOGS / ".go_live").exists()


def _sniper_stats(data: dict | None) -> dict:
    """Parse stats block, fall back to live compute from trades list."""
    empty = {"total_trades": 0, "resolved_trades": 0, "pending_trades": 0,
             "wins": 0, "losses": 0, "win_rate": 0.0, "realized_pnl": 0.0}
    if not data:
        return empty
    s = data.get("stats")
    if isinstance(s, dict) and "resolved_trades" in s:
        return s
    trades   = data.get("trades", [])
    resolved = [t for t in trades if t.get("resolved")]
    wins     = sum(1 for t in resolved if t.get("won"))
    return {
        "total_trades":    len(trades),
        "resolved_trades": len(resolved),
        "pending_trades":  len(trades) - len(resolved),
        "wins":            wins,
        "losses":          len(resolved) - wins,
        "win_rate":        round(wins / len(resolved) * 100, 1) if resolved else 0.0,
        "realized_pnl":    round(sum(t.get("pnl", 0) for t in resolved), 2),
    }


def _bar(wins: int, losses: int, width: int = 10) -> str:
    """Mini win/loss bar: ██████████ 8W 2L"""
    total = wins + losses
    if total == 0:
        return "──────────"
    filled = round(wins / total * width)
    return "█" * filled + "░" * (width - filled)


def _trend(trades: list, n: int = 5) -> str:
    """Last N resolved trades as arrows: ↑↑↓↑↑"""
    resolved = [t for t in trades if t.get("resolved")][-n:]
    return "".join("↑" if t.get("won") else "↓" for t in resolved) or "—"


# ── Commands ─────────────────────────────────────────────────────────────────

def cmd_status() -> str:
    mode = "🔴 LIVE" if _is_live() else "📋 PAPER"
    paused = " · ⏸ PAUSED" if _is_paused() else ""
    lines = [f"<b>APEX Status</b>  {mode}{paused}"]

    btc = _json(_POLY / "btc_5m_state.json")
    eth = _json(_POLY / "eth_5m_state.json")

    for label, data, sym in [("BTC", btc, "₿"), ("ETH", eth, "Ξ")]:
        if data:
            s = _sniper_stats(data)
            wr = f"{s['win_rate']}%" if s['resolved_trades'] else "—"
            pnl = s['realized_pnl']
            sign = "+" if pnl >= 0 else ""
            lines.append(
                f"\n{sym} <b>{label} Sniper</b>  ${data['bankroll']:.2f}\n"
                f"  {_bar(s['wins'], s['losses'])}  {s['wins']}W {s['losses']}L  {wr} WR\n"
                f"  PnL {sign}${pnl:.2f}  ·  {s['resolved_trades']} trades"
            )

    # Watchdog process summary
    wdog = _json(_LOGS / "watchdog_status.json")
    if wdog:
        procs = wdog.get("processes", {})
        running = [n for n, i in procs.items() if i.get("status") == "running"]
        lines.append(f"\n🟢 Running: {', '.join(running)}" if running else "\n⚫ No processes")

    lines.append(f"\n{datetime.now(DETROIT_TZ).strftime('%-I:%M %p ET')}")
    return "\n".join(lines)


def cmd_btc() -> str:
    data = _json(_POLY / "btc_5m_state.json")
    if not data:
        return "No BTC sniper data."
    s = _sniper_stats(data)
    trades = data.get("trades", [])
    wr = f"{s['win_rate']}%" if s['resolved_trades'] else "—"
    pnl = s['realized_pnl']
    sign = "+" if pnl >= 0 else ""
    lines = [
        f"<b>₿ BTC 5-Min Sniper</b>",
        f"Bankroll   ${data['bankroll']:.2f}",
        f"Record     {s['wins']}W / {s['losses']}L  ({wr})",
        f"PnL        {sign}${pnl:.2f}",
        f"Trades     {s['resolved_trades']} resolved · {s['pending_trades']} pending",
        f"Windows    {data.get('windows_scanned', 0)} scanned",
        f"Trend      {_trend(trades, 8)}",
        "",
        "<b>Last 3 trades:</b>",
    ]
    resolved = [t for t in trades if t.get("resolved")]
    for t in reversed(resolved[-3:]):
        result = "✅" if t.get("won") else "❌"
        lines.append(
            f"  {result} {t['direction']}  ${t.get('pnl', 0):+.2f}"
            f"  conf={int(t.get('confidence', 0)*100)}%"
            f"  edge={t.get('edge', 0)*100:.1f}%"
        )
    return "\n".join(lines)


def cmd_eth() -> str:
    data = _json(_POLY / "eth_5m_state.json")
    if not data:
        return "No ETH sniper data."
    s = _sniper_stats(data)
    trades = data.get("trades", [])
    wr = f"{s['win_rate']}%" if s['resolved_trades'] else "—"
    pnl = s['realized_pnl']
    sign = "+" if pnl >= 0 else ""
    lines = [
        f"<b>Ξ ETH 5-Min Sniper</b>",
        f"Bankroll   ${data['bankroll']:.2f}",
        f"Record     {s['wins']}W / {s['losses']}L  ({wr})",
        f"PnL        {sign}${pnl:.2f}",
        f"Trades     {s['resolved_trades']} resolved · {s['pending_trades']} pending",
        f"Windows    {data.get('windows_scanned', 0)} scanned",
        f"Trend      {_trend(trades, 8)}",
        "",
        "<b>Last 3 trades:</b>",
    ]
    resolved = [t for t in trades if t.get("resolved")]
    for t in reversed(resolved[-3:]):
        result = "✅" if t.get("won") else "❌"
        lines.append(
            f"  {result} {t['direction']}  ${t.get('pnl', 0):+.2f}"
            f"  conf={int(t.get('confidence', 0)*100)}%"
            f"  edge={t.get('edge', 0)*100:.1f}%"
        )
    return "\n".join(lines)


def cmd_balance() -> str:
    btc  = _json(_POLY / "btc_5m_state.json")
    eth  = _json(_POLY / "eth_5m_state.json")
    state = _json(STATE_FILE)
    lines = ["<b>Bankrolls</b>"]
    total = 0.0
    if btc:
        lines.append(f"₿ BTC Sniper    ${btc['bankroll']:.2f}")
        total += btc["bankroll"]
    if eth:
        lines.append(f"Ξ ETH Sniper    ${eth['bankroll']:.2f}")
        total += eth["bankroll"]
    if state:
        pnl = state.get("stats", {}).get("total_pnl", 0)
        lines.append(f"📊 Crypto Agents  PnL ${pnl:+.2f}")
    lines.append(f"\n<b>Total deployed  ${total:.2f}</b>")
    return "\n".join(lines)


def cmd_report() -> str:
    btc   = _json(_POLY / "btc_5m_state.json")
    eth   = _json(_POLY / "eth_5m_state.json")
    state = _json(STATE_FILE)
    lines = [
        f"<b>APEX Performance Report</b>",
        f"{datetime.now(DETROIT_TZ).strftime('%Y-%m-%d %-I:%M %p ET')}",
    ]

    for label, data, sym in [("BTC", btc, "₿"), ("ETH", eth, "Ξ")]:
        if data:
            s = _sniper_stats(data)
            wr = f"{s['win_rate']}%" if s['resolved_trades'] else "—"
            lines.append(f"\n{sym} <b>{label} Sniper</b>  ${data['bankroll']:.2f}")
            lines.append(f"  {s['wins']}W/{s['losses']}L  {wr}  PnL ${s['realized_pnl']:+.2f}")
            resolved = [t for t in data.get("trades", []) if t.get("resolved")]
            for t in resolved[-5:]:
                r = "✅" if t.get("won") else "❌"
                lines.append(f"  {r} {t['direction']} ${t.get('pnl',0):+.2f}  {t.get('edge',0)*100:.1f}% edge")

    if state:
        s = state.get("stats", {})
        lines.append(f"\n📊 <b>Crypto Agents</b>  {s.get('total_trades',0)} trades")
        lines.append(f"  ${s.get('total_pnl',0):+.2f} PnL · {s.get('wins',0)}W/{s.get('losses',0)}L")

    return "\n".join(lines)


def cmd_pause() -> str:
    _PAUSE_FILE.touch()
    return "⏸ Trading PAUSED. /resume to restart."


def cmd_resume() -> str:
    if _PAUSE_FILE.exists():
        _PAUSE_FILE.unlink()
    return "▶️ Trading RESUMED."


def cmd_live() -> str:
    _LIVE_FLAG = _LOGS / ".go_live"
    if _LIVE_FLAG.exists():
        return "Already in LIVE mode. /paper to switch back."
    try:
        sys.path.insert(0, str(_ROOT / "polymarket"))
        from polyconfig import POLY_PRIVATE_KEY
        if not POLY_PRIVATE_KEY:
            return "Cannot go live: POLY_PRIVATE_KEY not set in polyconfig.py."
    except Exception:
        pass
    _LIVE_FLAG.touch()
    return (
        "🔴 <b>LIVE MODE ACTIVATED</b>\n"
        "Watchdog restarts snipers in live mode within 15s.\n"
        "/paper to revert."
    )


def cmd_paper() -> str:
    _LIVE_FLAG = _LOGS / ".go_live"
    if not _LIVE_FLAG.exists():
        return "Already in PAPER mode."
    _LIVE_FLAG.unlink()
    return "📋 PAPER MODE restored. Watchdog restarts snipers within 15s."


def cmd_eth_live() -> str:
    flag = _LOGS / ".go_live_eth"
    if flag.exists():
        return "ETH already LIVE. /eth_paper to revert."
    try:
        sys.path.insert(0, str(_ROOT / "polymarket"))
        from polyconfig import POLY_PRIVATE_KEY
        if not POLY_PRIVATE_KEY:
            return "Cannot go ETH live: POLY_PRIVATE_KEY not set."
    except Exception:
        pass
    flag.touch()
    return "🔴 <b>ETH LIVE MODE ACTIVATED</b>\nWatchdog restarts ETH sniper in ~15s.\n/eth_paper to revert."


def cmd_eth_paper() -> str:
    flag = _LOGS / ".go_live_eth"
    if not flag.exists():
        return "ETH already in PAPER mode."
    flag.unlink()
    return "📋 ETH PAPER MODE restored. Watchdog restarts ETH sniper within 15s."


def cmd_ping() -> str:
    state   = _json(STATE_FILE)
    updated = state.get("updated_at", "?")[:19] if state else "?"
    p       = " · PAUSED" if _is_paused() else ""
    mode    = " · LIVE" if _is_live() else " · PAPER"
    return f"🏓 PONG — {updated} UTC{p}{mode}"


def cmd_help() -> str:
    return (
        "<b>APEX Commands</b>\n\n"
        "/status   — live system overview\n"
        "/btc      — BTC 5-min sniper detail\n"
        "/eth      — ETH 5-min sniper detail\n"
        "/balance  — all bankrolls\n"
        "/report   — full performance breakdown\n"
        "/live     — BTC → LIVE\n"
        "/paper    — BTC → PAPER\n"
        "/eth_live  — ETH → LIVE\n"
        "/eth_paper — ETH → PAPER\n"
        "/pause    — pause all trading\n"
        "/resume   — resume trading\n"
        "/ping     — health check\n"
        "/help     — this list"
    )


COMMANDS = {
    "/status": cmd_status,
    "/btc":    cmd_btc,
    "/eth":    cmd_eth,
    "/balance": cmd_balance,
    "/report": cmd_report,
    "/pause":  cmd_pause,
    "/resume": cmd_resume,
    "/live":   cmd_live,
    "/paper":  cmd_paper,
    "/eth_live":  cmd_eth_live,
    "/eth_paper": cmd_eth_paper,
    "/ping":   cmd_ping,
    "/help":   cmd_help,
    "ping":    cmd_ping,
}


# ── Hourly Digest ─────────────────────────────────────────────────────────────

def _live_clob_balance() -> float | None:
    """Query the live Polymarket CLOB collateral balance for the configured wallet."""
    try:
        sys.path.insert(0, str(_ROOT / "polymarket"))
        from polyconfig import POLY_PRIVATE_KEY
        if not POLY_PRIVATE_KEY:
            return None
        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import BalanceAllowanceParams, AssetType
        client = ClobClient("https://clob.polymarket.com", key=POLY_PRIVATE_KEY, chain_id=137)
        client.set_api_creds(client.create_or_derive_api_creds())
        resp = client.get_balance_allowance(
            BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
        )
        return int(resp["balance"]) / 1e6
    except Exception as e:
        print(f"[TG] live CLOB balance failed: {e}")
        return None


def _build_digest() -> str | None:
    btc = _json(_POLY / "btc_5m_state.json")
    eth = _json(_POLY / "eth_5m_state.json")

    if not btc and not eth:
        return None

    btc_live = (_LOGS / ".go_live").exists()
    eth_live = (_LOGS / ".go_live_eth").exists()
    paused   = _is_paused()

    now_et = datetime.now(DETROIT_TZ)
    header_mode = "🔴 LIVE" if (btc_live or eth_live) else "📋 PAPER"
    if paused:
        header_mode += " · ⏸"

    live_clob = _live_clob_balance()

    lines = [
        f"<b>⚡ APEX</b>  <code>{now_et.strftime('%-I:%M %p ET')}</code>  {header_mode}",
        "━━━━━━━━━━━━━━━━━━━━",
    ]

    total_bank = 0.0
    total_pnl  = 0.0

    for label, data, sym, is_live in [
        ("BTC", btc, "₿", btc_live),
        ("ETH", eth, "Ξ", eth_live),
    ]:
        if not data:
            continue
        s   = _sniper_stats(data)
        br  = data.get("bankroll", 0.0)
        pnl = s["realized_pnl"]
        wr  = f"{s['win_rate']:.0f}%" if s["resolved_trades"] else "—"
        tag = "🔴 LIVE" if is_live else "📋 PAPER"
        bar = _bar(s["wins"], s["losses"])
        trend = _trend(data.get("trades", []), 5)

        total_bank += br
        total_pnl  += pnl

        lines.append(
            f"\n{sym} <b>{label}</b> · <code>${br:.2f}</code> · {tag}\n"
            f"   {bar}\n"
            f"   {s['wins']}W · {s['losses']}L · {wr}  ·  PnL <b>{pnl:+.2f}</b>\n"
            f"   last 5: {trend}"
        )

    lines.append("\n━━━━━━━━━━━━━━━━━━━━")
    if live_clob is not None:
        lines.append(f"💰 <b>Live CLOB</b> <code>${live_clob:.2f}</code>")
    lines.append(f"📦 <b>Portfolio</b> <code>${total_bank:.2f}</code>  ({total_pnl:+.2f})")

    return "\n".join(lines)


def _should_digest() -> bool:
    now = datetime.now(DETROIT_TZ)
    try:
        if _DIGEST_FILE.exists():
            last_hour = int(_DIGEST_FILE.read_text().strip())
            return now.hour != last_hour
    except Exception:
        pass
    return True


def _mark_digest():
    try:
        _DIGEST_FILE.write_text(str(datetime.now(DETROIT_TZ).hour))
    except Exception:
        pass


# ── Claude AI (optional) ──────────────────────────────────────────────────────

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


# ── Heartbeat (backwards compat) ──────────────────────────────────────────────

async def send_heartbeat(report: dict):
    pass  # Handled by hourly digest


# ── Main Loop ─────────────────────────────────────────────────────────────────

def run_bot():
    print("[TG] Bot started.")
    last_id = None

    while True:
        updates = _poll(last_id)
        for update in updates:
            last_id = update["update_id"] + 1
            msg     = update.get("message", {})
            if str(msg.get("chat", {}).get("id")) != str(TELEGRAM_CHAT_ID):
                continue

            text = msg.get("text", "").strip()
            if not text:
                continue

            first = text.split()[0]
            if first.startswith("/"):
                cmd     = first.split("@")[0].lower()
                handler = COMMANDS.get(cmd)
                if handler:
                    try:
                        _send(handler())
                    except Exception as e:
                        _send(f"Error: {e}")
                else:
                    _send(f"Unknown command: {cmd}\n/help for the list")
            else:
                _send(_ai_reply(text))

        if _should_digest():
            digest = _build_digest()
            if digest:
                _send(digest)
            _mark_digest()

        time.sleep(1)


if __name__ == "__main__":
    run_bot()
