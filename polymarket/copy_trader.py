"""
APEX -- Polymarket Copy Trader
================================================================
Monitors Polymarket for whale flow signals and copies high-conviction
trades from profitable wallets.

Approach:
  1. Scan CLOB API for recent large trades (>= MIN_WHALE_TRADE_SIZE)
  2. Track wallet PnL over time to build a leaderboard
  3. Copy trades from top-performing wallets with Kelly sizing
  4. Manage risk with consecutive loss cooldowns

Usage:
    python3 polymarket/copy_trader.py           # paper mode
    python3 polymarket/copy_trader.py --live     # live (needs wallet)
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
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
    CLOB_API, GAMMA_API, DATA_DIR,
    STARTING_BANKROLL, KELLY_FRACTION, MAX_POSITION_PCT,
    MIRROR_RATIO, MAX_COPY_SIZE, MIN_WHALE_TRADE_SIZE,
    MAX_CONSECUTIVE_LOSSES, COOLDOWN_HOURS, TOP_N_TRADERS,
    COPY_SCAN_INTERVAL, PAPER_TRADE_ONLY,
)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

STATE_PATH = DATA_DIR / "copy_trader_state.json"
WHALE_DB_PATH = DATA_DIR / "whale_stats.json"


# -- Telegram ------------------------------------------------------------------

def _tg(text: str):
    if not TELEGRAM_BOT_TOKEN:
        return
    data = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
    }).encode()
    try:
        urllib.request.urlopen(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data=data, timeout=10,
        )
    except Exception:
        pass


# -- API Helpers ---------------------------------------------------------------

def _api_get(url: str, params: dict = None) -> dict | list | None:
    """GET request with requests/urllib fallback."""
    if _HAS_REQUESTS:
        try:
            r = _req.get(url, params=params, headers=_HEADERS, timeout=15)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
    try:
        full = url
        if params:
            full = url + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(full, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as f:
            return json.loads(f.read().decode())
    except Exception:
        return None


def fetch_recent_trades(limit: int = 200) -> list[dict]:
    """Fetch recent trades from Polymarket CLOB API."""
    data = _api_get(f"{CLOB_API}/trades", {"limit": limit})
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("data", data.get("trades", []))
    return []


def fetch_market_info(condition_id: str) -> dict | None:
    """Fetch market details from Gamma API."""
    data = _api_get(f"{GAMMA_API}/markets", {"condition_id": condition_id})
    if isinstance(data, list) and data:
        return data[0]
    return data if isinstance(data, dict) else None


# -- Whale Database ------------------------------------------------------------

class WhaleDB:
    """Track wallet performance and identify profitable traders."""

    def __init__(self):
        self.wallets: dict[str, dict] = {}  # address -> stats
        self._load()

    def _load(self):
        if WHALE_DB_PATH.exists():
            try:
                self.wallets = json.loads(WHALE_DB_PATH.read_text())
            except Exception:
                self.wallets = {}

    def save(self):
        WHALE_DB_PATH.write_text(json.dumps(self.wallets, indent=2))

    def record_trade(self, address: str, trade: dict):
        """Record a trade for a wallet."""
        if address not in self.wallets:
            self.wallets[address] = {
                "address": address,
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "total_volume": 0.0,
                "net_pnl": 0.0,
                "last_seen": "",
                "recent_trades": [],
            }

        w = self.wallets[address]
        w["trades"] += 1
        w["total_volume"] += trade.get("size", 0)
        w["last_seen"] = datetime.now(timezone.utc).isoformat()
        w["recent_trades"] = (w["recent_trades"] + [trade])[-50:]  # last 50
        self.save()

    def record_result(self, address: str, won: bool, pnl: float):
        """Record a trade result for a wallet."""
        if address not in self.wallets:
            return
        w = self.wallets[address]
        if won:
            w["wins"] += 1
        else:
            w["losses"] += 1
        w["net_pnl"] += pnl
        self.save()

    def get_top_traders(self, n: int = TOP_N_TRADERS) -> list[dict]:
        """Return top N wallets by win rate (min 5 trades)."""
        qualified = []
        for addr, w in self.wallets.items():
            total = w["wins"] + w["losses"]
            if total < 5:
                continue
            wr = w["wins"] / total if total > 0 else 0
            qualified.append({
                "address": addr,
                "win_rate": round(wr * 100, 1),
                "trades": w["trades"],
                "resolved": total,
                "net_pnl": round(w["net_pnl"], 2),
                "volume": round(w["total_volume"], 2),
                "last_seen": w["last_seen"],
            })

        qualified.sort(key=lambda x: (x["win_rate"], x["net_pnl"]), reverse=True)
        return qualified[:n]


# -- Copy Trader State ---------------------------------------------------------

class CopyTraderState:
    def __init__(self):
        self.bankroll = STARTING_BANKROLL
        self.positions: dict[str, dict] = {}   # condition_id -> position
        self.history: list[dict] = []
        self.consecutive_losses = 0
        self.cooldown_until: str | None = None
        self.seen_trades: set[str] = set()     # trade IDs we've processed
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
                self.seen_trades = set(d.get("seen_trades", []))
            except Exception:
                pass

    def save(self):
        STATE_PATH.write_text(json.dumps({
            "bankroll": self.bankroll,
            "positions": self.positions,
            "history": self.history[-200:],
            "consecutive_losses": self.consecutive_losses,
            "cooldown_until": self.cooldown_until,
            "seen_trades": list(self.seen_trades)[-1000:],
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

    def open_position(self, condition_id: str, trade: dict):
        self.positions[condition_id] = trade
        if not PAPER_TRADE_ONLY:
            self.bankroll -= trade["bet_size"]
        self.save()

    def close_position(self, condition_id: str, won: bool, pnl: float):
        if condition_id in self.positions:
            pos = self.positions.pop(condition_id)
            pos["resolved"] = True
            pos["won"] = won
            pos["pnl"] = round(pnl, 2)
            self.history.append(pos)

            self.bankroll += pnl
            if won:
                self.consecutive_losses = 0
            else:
                self.consecutive_losses += 1
                if self.consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
                    from datetime import timedelta
                    self.cooldown_until = (
                        datetime.now(timezone.utc) + timedelta(hours=COOLDOWN_HOURS)
                    ).isoformat()
            self.save()

    def summary(self) -> str:
        resolved = [h for h in self.history if h.get("resolved")]
        wins = sum(1 for h in resolved if h.get("won"))
        total = len(resolved)
        wr = round(wins / total * 100, 1) if total else 0
        total_pnl = sum(h.get("pnl", 0) for h in resolved)
        return (f"Bankroll: ${self.bankroll:.2f} | "
                f"Trades: {total} | WR: {wr}% | "
                f"PnL: ${total_pnl:+.2f} | "
                f"Open: {len(self.positions)}")


# -- Core Logic ----------------------------------------------------------------

def detect_whale_trades(trades: list[dict]) -> list[dict]:
    """Filter trades for whale-sized orders."""
    whales = []
    for t in trades:
        size = float(t.get("size", t.get("amount", 0)) or 0)
        if size >= MIN_WHALE_TRADE_SIZE:
            whales.append({
                "trade_id": t.get("id", t.get("tradeID", "")),
                "maker": t.get("maker", t.get("maker_address", "")),
                "taker": t.get("taker", t.get("taker_address", "")),
                "asset_id": t.get("asset_id", t.get("token_id", "")),
                "condition_id": t.get("condition_id", t.get("market", "")),
                "side": t.get("side", "BUY"),
                "size": size,
                "price": float(t.get("price", 0) or 0),
                "timestamp": t.get("timestamp", t.get("created_at", "")),
                "outcome": t.get("outcome", t.get("outcome_index", "")),
            })
    return whales


def size_copy_trade(whale_size: float, whale_price: float,
                    bankroll: float) -> float | None:
    """
    Size a copy trade based on whale trade.
    Uses MIRROR_RATIO of whale size, capped by MAX_COPY_SIZE and bankroll %.
    """
    raw_size = whale_size * MIRROR_RATIO
    capped = min(raw_size, MAX_COPY_SIZE)
    bankroll_cap = bankroll * MAX_POSITION_PCT

    bet_size = min(capped, bankroll_cap)
    if bet_size < 0.50:
        return None
    return round(bet_size, 2)


def _cycle(state: CopyTraderState, whale_db: WhaleDB):
    """One scan cycle: fetch trades, detect whales, copy if profitable."""
    if state.is_cooling_down():
        print(f"[CopyTrader] Cooling down until {state.cooldown_until}")
        return

    trades = fetch_recent_trades(200)
    if not trades:
        print("[CopyTrader] No trades returned from API")
        return

    whale_trades = detect_whale_trades(trades)
    new_whales = [w for w in whale_trades if w["trade_id"] not in state.seen_trades]

    if not new_whales:
        print(f"[CopyTrader] {len(trades)} trades scanned, "
              f"{len(whale_trades)} whale-sized, 0 new")
        return

    # Record all whale trades in the database
    for w in new_whales:
        state.seen_trades.add(w["trade_id"])
        address = w["maker"] or w["taker"]
        if address:
            whale_db.record_trade(address, w)

    # Get top performing wallets
    top_traders = whale_db.get_top_traders()
    top_addresses = {t["address"] for t in top_traders}

    copied = 0
    for w in new_whales:
        address = w["maker"] or w["taker"]

        # Only copy from profitable wallets (or all if we don't have enough data yet)
        is_top = address in top_addresses
        has_data = whale_db.wallets.get(address, {}).get("trades", 0) >= 3

        if has_data and not is_top:
            continue

        cid = w["condition_id"]
        if cid in state.positions:
            continue

        bet_size = size_copy_trade(w["size"], w["price"], state.bankroll)
        if bet_size is None:
            continue

        # Determine direction from the whale trade
        side = w.get("side", "BUY").upper()
        outcome = w.get("outcome", "")
        direction = "YES" if side == "BUY" else "NO"

        position = {
            "condition_id": cid,
            "whale_address": address,
            "whale_size": w["size"],
            "direction": direction,
            "bet_size": bet_size,
            "entry_price": w["price"],
            "whale_trade_id": w["trade_id"],
            "is_top_trader": is_top,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "resolved": False,
        }

        state.open_position(cid, position)
        copied += 1

        whale_wr = "NEW"
        for t in top_traders:
            if t["address"] == address:
                whale_wr = f"{t['win_rate']}%"
                break

        print(f"  [Copy] {direction} ${bet_size:.2f} | "
              f"whale=${w['size']:.0f} | addr={address[:10]}... | "
              f"whale_wr={whale_wr}")

    print(f"[CopyTrader] {len(trades)} trades -> {len(new_whales)} new whales -> "
          f"{copied} copied | {state.summary()}")
    state.save()


# -- Main Loop -----------------------------------------------------------------

def run_copy_trader():
    state = CopyTraderState()
    whale_db = WhaleDB()
    mode = "PAPER" if PAPER_TRADE_ONLY else "LIVE"

    print(f"[CopyTrader] Started ({mode})")
    print(f"[CopyTrader] Config: mirror={MIRROR_RATIO*100:.0f}%, "
          f"max=${MAX_COPY_SIZE}, min_whale=${MIN_WHALE_TRADE_SIZE}, "
          f"top_n={TOP_N_TRADERS}")
    print(f"[CopyTrader] {state.summary()}")

    # Write status for dashboard
    _write_status(state, whale_db)

    while True:
        try:
            _cycle(state, whale_db)
            _write_status(state, whale_db)
        except Exception as e:
            print(f"[CopyTrader] cycle error: {e}")
            import traceback
            traceback.print_exc()

        time.sleep(COPY_SCAN_INTERVAL)


def _write_status(state: CopyTraderState, whale_db: WhaleDB):
    """Write status file for dashboard consumption."""
    status = {
        "bankroll": state.bankroll,
        "positions": state.positions,
        "history": state.history[-100:],
        "consecutive_losses": state.consecutive_losses,
        "cooldown_until": state.cooldown_until,
        "top_traders": whale_db.get_top_traders(),
        "total_wallets_tracked": len(whale_db.wallets),
        "updated": datetime.now(timezone.utc).isoformat(),
    }
    (DATA_DIR / "copy_trader_status.json").write_text(json.dumps(status, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Polymarket Copy Trader")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()

    if args.live:
        from polymarket.polyconfig import POLY_PRIVATE_KEY
        if not POLY_PRIVATE_KEY:
            print("[CopyTrader] --live requires POLY_PRIVATE_KEY")
            sys.exit(1)

    run_copy_trader()


if __name__ == "__main__":
    main()
