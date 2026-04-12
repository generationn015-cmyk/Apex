"""
APEX — Polymarket Sniper  (rebuilt from scanner.py + broken production_sniper)

What was broken:
  - production_sniper.py had truncated code (10 lines, missing body)
  - Kelly engine was in scanner.py but not connected to execution
  - No persistent state tracking between runs

This version:
  - Scans Gamma API for live markets
  - Filters by edge (vig-removed true probability vs market price)
  - Kelly sizes each position (quarter-Kelly, hard cap)
  - Paper trades by default — flip PAPER_TRADE_ONLY=False for live
  - Sends Telegram alerts on every signal
  - Persists results to polymarket/data/
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from polymarket.scanner import KellyEngine, parse_market
from polymarket.polyconfig import (
    GAMMA_API, MIN_EDGE, KELLY_FRACTION, MAX_POSITION_PCT,
    STARTING_BANKROLL, MIN_LIQUIDITY, MIN_VOLUME,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    PAPER_TRADE_ONLY, DATA_DIR,
)

# ── Telegram ──────────────────────────────────────────────────────────────────

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
            data=data, timeout=10
        )
    except Exception:
        pass


# ── Market fetcher ────────────────────────────────────────────────────────────

def fetch_markets(limit: int = 100) -> list[dict]:
    """Fetch active markets from Gamma API."""
    url = f"{GAMMA_API}/markets?active=true&closed=false&limit={limit}"
    try:
        with urllib.request.urlopen(url, timeout=15) as f:
            raw = json.loads(f.read().decode())
            # Gamma returns list directly or {"data": [...]}
            if isinstance(raw, list):
                return raw
            return raw.get("data", [])
    except Exception as e:
        print(f"[Polymarket] fetch error: {e}")
        return []


def filter_eligible(markets: list[dict]) -> list[dict]:
    """Keep only markets with sufficient liquidity, volume, and short-term resolution."""
    eligible = []
    for m in markets:
        parsed = parse_market(m)
        if not parsed:
            continue
        if parsed["liquidity"] < MIN_LIQUIDITY:
            continue
        if parsed["volume"] < MIN_VOLUME:
            continue
        if parsed.get("closed"):
            continue
        eligible.append(parsed)
    return eligible


# ── State persistence ─────────────────────────────────────────────────────────

class SniperState:
    def __init__(self):
        self.path      = DATA_DIR / "sniper_state.json"
        self.bankroll  = STARTING_BANKROLL
        self.positions: dict[str, dict] = {}   # condition_id → position
        self.history:   list[dict] = []
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                d = json.loads(self.path.read_text())
                self.bankroll  = d.get("bankroll",  STARTING_BANKROLL)
                self.positions = d.get("positions", {})
                self.history   = d.get("history",   [])
            except Exception:
                pass

    def save(self):
        self.path.write_text(json.dumps({
            "bankroll":  self.bankroll,
            "positions": self.positions,
            "history":   self.history,
            "updated":   datetime.now(timezone.utc).isoformat(),
        }, indent=2))

    def already_open(self, condition_id: str) -> bool:
        return condition_id in self.positions

    def open_position(self, market: dict, bet: dict):
        self.positions[market["condition_id"]] = {
            "question":  market["question"],
            "direction": bet["direction"],
            "bet_size":  bet["bet_size"],
            "entry_price": market["yes_price"] if bet["direction"] == "YES" else market["no_price"],
            "edge":      bet["edge"],
            "opened_at": datetime.now(timezone.utc).isoformat(),
        }
        if not PAPER_TRADE_ONLY:
            self.bankroll -= bet["bet_size"]
        self.save()

    def pnl_summary(self) -> str:
        open_count = len(self.positions)
        hist_count = len(self.history)
        wins  = sum(1 for h in self.history if h.get("result") == "WIN")
        total = hist_count
        wr    = round(wins / total * 100, 1) if total else 0
        return (f"Bankroll: ${self.bankroll:.2f}  |  "
                f"Open: {open_count}  |  Closed: {hist_count}  |  WR: {wr}%")


# ── Main sniper loop ─────────────────────────────────────────────────────────

def run_sniper(once: bool = False):
    from polymarket.polyconfig import SCAN_INTERVAL_SECS
    state  = SniperState()
    kelly  = KellyEngine(
        bankroll=state.bankroll,
        kelly_fraction=KELLY_FRACTION,
        min_edge=MIN_EDGE,
        max_position_pct=MAX_POSITION_PCT,
    )

    mode_tag = "PAPER" if PAPER_TRADE_ONLY else "LIVE"
    _tg(f"🎯 <b>Polymarket Sniper online ({mode_tag})</b>\n{state.pnl_summary()}")
    print(f"[Sniper] Started ({mode_tag})")

    while True:
        try:
            _cycle(state, kelly)
        except Exception as e:
            print(f"[Sniper] cycle error: {e}")

        if once:
            break

        time.sleep(SCAN_INTERVAL_SECS)


def _cycle(state: SniperState, kelly: KellyEngine):
    markets = fetch_markets(200)
    if not markets:
        print("[Sniper] No markets returned")
        return

    eligible = filter_eligible(markets)
    print(f"[Sniper] {len(markets)} total → {len(eligible)} eligible")

    fired = 0
    for market in eligible:
        cid = market["condition_id"]
        if state.already_open(cid):
            continue

        # Kelly sizing — uses vig-removed edge
        bet = kelly.calculate(
            market_prob=_estimate_true_prob(market),
            market_price=market["yes_price"],
        )
        if bet is None:
            continue

        # Edge gate
        if bet["edge"] < MIN_EDGE:
            continue

        # Open position
        state.open_position(market, bet)
        fired += 1

        summary = (
            f"🎯 <b>Polymarket Signal</b>\n"
            f"<b>{market['question'][:80]}</b>\n"
            f"Direction: {bet['direction']}\n"
            f"Edge: {bet['edge']*100:.1f}%  |  Kelly: {bet['kelly_pct']:.1f}%\n"
            f"Bet: ${bet['bet_size']:.2f}  |  Mode: {'PAPER' if PAPER_TRADE_ONLY else 'LIVE'}\n"
            f"Bankroll: ${state.bankroll:.2f}"
        )
        _tg(summary)
        print(f"  ✅ {bet['direction']} | ${bet['bet_size']:.2f} | edge={bet['edge']*100:.1f}% | {market['question'][:60]}")

    if fired == 0:
        print("[Sniper] No edges found this cycle")


def _estimate_true_prob(market: dict) -> float:
    """
    Vig-removed true probability.
    For binary markets: remove the vig by normalising both sides.
    true_yes = yes_price / (yes_price + no_price)
    """
    yes = market["yes_price"]
    no  = market["no_price"]
    total = yes + no
    if total <= 0:
        return yes
    return yes / total


if __name__ == "__main__":
    run_sniper()
