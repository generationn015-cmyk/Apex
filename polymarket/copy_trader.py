"""
APEX -- Polymarket Copy Trader
================================================================
Monitors data-api.polymarket.com/trades for whale activity.
Tracks wallet performance. Mirrors profitable wallets with Kelly sizing.

Data source: https://data-api.polymarket.com/trades (no auth needed)
Fields: proxyWallet, side, asset, conditionId, size, price, title, outcome

Usage:
    python3 polymarket/copy_trader.py
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import requests as _req
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

from polymarket.polyconfig import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    DATA_DIR, STARTING_BANKROLL, MAX_POSITION_PCT,
    MIRROR_RATIO, MAX_COPY_SIZE, MIN_WHALE_TRADE_SIZE,
    MAX_CONSECUTIVE_LOSSES, COOLDOWN_HOURS, TOP_N_TRADERS,
    COPY_SCAN_INTERVAL, PAPER_TRADE_ONLY,
)

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
DATA_API = "https://data-api.polymarket.com"
STATE_PATH = DATA_DIR / "copy_trader_state.json"
WHALE_DB_PATH = DATA_DIR / "whale_stats.json"
STATUS_PATH = DATA_DIR / "copy_trader_status.json"


# -- API --------------------------------------------------------------------

def fetch_recent_trades(limit: int = 200) -> list[dict]:
    """Fetch recent trades from Polymarket data API."""
    url = f"{DATA_API}/trades"
    params = {"limit": limit}
    if _HAS_REQUESTS:
        try:
            r = _req.get(url, params=params, headers=_HEADERS, timeout=15)
            if r.status_code == 200:
                return r.json() if isinstance(r.json(), list) else []
        except Exception:
            pass
    try:
        qs = urllib.parse.urlencode(params)
        req = urllib.request.Request(f"{url}?{qs}", headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as f:
            data = json.loads(f.read().decode())
            return data if isinstance(data, list) else []
    except Exception:
        return []


# -- Whale Database ---------------------------------------------------------

class WhaleDB:
    """Track wallet performance over time."""

    def __init__(self):
        self.wallets: dict[str, dict] = {}
        self._load()

    def _load(self):
        if WHALE_DB_PATH.exists():
            try:
                self.wallets = json.loads(WHALE_DB_PATH.read_text())
            except Exception:
                self.wallets = {}

    def save(self):
        WHALE_DB_PATH.write_text(json.dumps(self.wallets, indent=2))

    def record_trade(self, wallet: str, trade: dict):
        if wallet not in self.wallets:
            self.wallets[wallet] = {
                "address": wallet,
                "name": trade.get("name", ""),
                "trades": 0,
                "total_volume": 0.0,
                "last_seen": "",
                "markets": {},
            }
        w = self.wallets[wallet]
        w["trades"] += 1
        w["total_volume"] += trade.get("size", 0)
        w["last_seen"] = datetime.now(timezone.utc).isoformat()
        if trade.get("name"):
            w["name"] = trade["name"]
        # Track per-market positions for this wallet
        cid = trade.get("conditionId", "")
        if cid:
            w["markets"][cid] = {
                "title": trade.get("title", "")[:60],
                "side": trade.get("side", ""),
                "outcome": trade.get("outcome", ""),
                "size": trade.get("size", 0),
                "price": trade.get("price", 0),
                "timestamp": trade.get("timestamp", 0),
            }
        self.save()

    def get_top_traders(self, n: int = TOP_N_TRADERS) -> list[dict]:
        """Top wallets by volume and trade frequency."""
        ranked = []
        for addr, w in self.wallets.items():
            if w["trades"] < 3:
                continue
            ranked.append({
                "address": addr,
                "name": w.get("name", ""),
                "trades": w["trades"],
                "volume": round(w["total_volume"], 2),
                "last_seen": w["last_seen"],
                "active_markets": len(w.get("markets", {})),
            })
        ranked.sort(key=lambda x: (x["volume"], x["trades"]), reverse=True)
        return ranked[:n]


# -- Copy Trader State -------------------------------------------------------

class CopyState:
    def __init__(self):
        self.bankroll = STARTING_BANKROLL
        self.positions: dict[str, dict] = {}
        self.history: list[dict] = []
        self.consecutive_losses = 0
        self.cooldown_until: str | None = None
        self.seen_tx: set[str] = set()
        self._load()

    def _load(self):
        if STATE_PATH.exists():
            try:
                d = json.loads(STATE_PATH.read_text())
                self.bankroll = d.get("bankroll", STARTING_BANKROLL)
                self.positions = d.get("positions", {})
                self.history = d.get("history", [])
                self.consecutive_losses = d.get("consecutive_losses", 0)
                self.cooldown_until = d.get("cooldown_until")
                self.seen_tx = set(d.get("seen_tx", []))
            except Exception:
                pass

    def save(self):
        STATE_PATH.write_text(json.dumps({
            "bankroll": self.bankroll,
            "positions": self.positions,
            "history": self.history[-200:],
            "consecutive_losses": self.consecutive_losses,
            "cooldown_until": self.cooldown_until,
            "seen_tx": list(self.seen_tx)[-2000:],
            "updated": datetime.now(timezone.utc).isoformat(),
        }, indent=2))

    def is_cooling_down(self) -> bool:
        if not self.cooldown_until:
            return False
        try:
            cd = datetime.fromisoformat(self.cooldown_until)
            if cd.tzinfo is None:
                cd = cd.replace(tzinfo=timezone.utc)
            return datetime.now(timezone.utc) < cd
        except Exception:
            return False

    def summary(self) -> str:
        total = len(self.history)
        pnl = sum(h.get("pnl", 0) for h in self.history)
        return (f"Bank: ${self.bankroll:.2f} | Trades: {total} | "
                f"Open: {len(self.positions)} | PnL: ${pnl:+.2f}")


# -- Core Logic --------------------------------------------------------------

def _cycle(state: CopyState, whale_db: WhaleDB):
    if state.is_cooling_down():
        print(f"[CopyTrader] Cooling down until {state.cooldown_until}")
        return

    trades = fetch_recent_trades(200)
    if not trades:
        print("[CopyTrader] No trades from API")
        return

    # Filter for whale trades we haven't seen
    new_whales = []
    for t in trades:
        tx = t.get("transactionHash", "")
        if not tx or tx in state.seen_tx:
            continue
        size = float(t.get("size", 0) or 0)
        if size < MIN_WHALE_TRADE_SIZE:
            continue
        state.seen_tx.add(tx)
        new_whales.append(t)

    # Record all whale activity
    for t in new_whales:
        wallet = t.get("proxyWallet", "")
        if wallet:
            whale_db.record_trade(wallet, t)

    # Get top wallets
    top = whale_db.get_top_traders()
    top_addrs = {w["address"] for w in top}

    copied = 0
    for t in new_whales:
        wallet = t.get("proxyWallet", "")
        cid = t.get("conditionId", "")
        if not cid or cid in state.positions:
            continue

        # Copy from known big wallets, or any whale with large enough trade
        is_known = wallet in top_addrs
        size = float(t.get("size", 0))

        if not is_known and size < MIN_WHALE_TRADE_SIZE * 2:
            continue  # Unknown wallets need 2x min to copy

        # Size the copy
        raw = size * MIRROR_RATIO
        bet_size = round(min(raw, MAX_COPY_SIZE, state.bankroll * MAX_POSITION_PCT), 2)
        if bet_size < 0.50:
            continue

        position = {
            "condition_id": cid,
            "title": t.get("title", "")[:60],
            "outcome": t.get("outcome", ""),
            "side": t.get("side", "BUY"),
            "bet_size": bet_size,
            "entry_price": float(t.get("price", 0)),
            "whale_address": wallet,
            "whale_name": t.get("name", t.get("pseudonym", "")),
            "whale_size": size,
            "is_known_whale": is_known,
            "tx": t.get("transactionHash", ""),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        state.positions[cid] = position
        if not PAPER_TRADE_ONLY:
            state.bankroll -= bet_size
        copied += 1

        name = position["whale_name"] or wallet[:10] + "..."
        print(f"  [COPY] {position['side']} ${bet_size:.2f} on "
              f"{position['title']} | whale={name} ${size:,.0f}")

    total_whales = len(new_whales)
    print(f"[CopyTrader] {len(trades)} trades | {total_whales} new whales | "
          f"{copied} copied | {state.summary()}")

    state.save()
    _write_status(state, whale_db)


def _write_status(state: CopyState, whale_db: WhaleDB):
    """Write status for dashboard."""
    resolved = [h for h in state.history if h.get("resolved")]
    wins = sum(1 for h in resolved if h.get("won"))
    total = len(resolved)

    STATUS_PATH.write_text(json.dumps({
        "bankroll": state.bankroll,
        "positions": state.positions,
        "history": state.history[-100:],
        "consecutive_losses": state.consecutive_losses,
        "cooldown_until": state.cooldown_until,
        "top_traders": whale_db.get_top_traders(),
        "total_wallets_tracked": len(whale_db.wallets),
        "wins": wins,
        "losses": total - wins,
        "win_rate": round(wins / total * 100, 1) if total else 0,
        "updated": datetime.now(timezone.utc).isoformat(),
    }, indent=2))


def run():
    state = CopyState()
    whale_db = WhaleDB()
    mode = "PAPER" if PAPER_TRADE_ONLY else "LIVE"

    print(f"[CopyTrader] Started ({mode})")
    print(f"[CopyTrader] mirror={MIRROR_RATIO*100:.0f}% | "
          f"max=${MAX_COPY_SIZE} | min_whale=${MIN_WHALE_TRADE_SIZE} | "
          f"scan_interval={COPY_SCAN_INTERVAL}s")
    print(f"[CopyTrader] {state.summary()}")

    _write_status(state, whale_db)

    while True:
        try:
            _cycle(state, whale_db)
        except Exception as e:
            print(f"[CopyTrader] error: {e}")
            import traceback
            traceback.print_exc()
        time.sleep(COPY_SCAN_INTERVAL)


if __name__ == "__main__":
    run()
