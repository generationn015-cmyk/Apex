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

try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

from polymarket.scanner import KellyEngine, parse_market, is_btc_market
from polymarket.polyconfig import (
    GAMMA_API, MIN_EDGE, KELLY_FRACTION, MAX_POSITION_PCT,
    STARTING_BANKROLL, MIN_LIQUIDITY, MIN_VOLUME,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    PAPER_TRADE_ONLY, DATA_DIR,
    BTC_SNIPER_ENABLED, BTC_SNIPER_MAX_MINUTES, BTC_SNIPER_MIN_MINUTES,
    BTC_SNIPER_MIN_EDGE, BTC_SNIPER_MAX_BET_PCT,
)

# ── Telegram ──────────────────────────────────────────────────────────────────

def _tg(text: str):
    """Write notification to shared queue file instead of sending directly."""
    try:
        queue_path = DATA_DIR / "notification_queue.jsonl"
        entry = json.dumps({
            "source": "polymarket_sniper",
            "text": text,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        with open(queue_path, "a") as f:
            f.write(entry + "\n")
    except Exception:
        pass


# ── Market fetcher ────────────────────────────────────────────────────────────

def _gamma_get(params: dict) -> list[dict]:
    """Single Gamma API call; returns list of raw market dicts."""
    url = f"{GAMMA_API}/markets"
    if _HAS_REQUESTS:
        try:
            r = _requests.get(url, params=params, headers=_HEADERS, timeout=15)
            if r.status_code == 200:
                raw = r.json()
                return raw if isinstance(raw, list) else raw.get("data", [])
        except Exception:
            pass
    try:
        full_url = url + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(full_url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as f:
            raw = json.loads(f.read().decode())
            return raw if isinstance(raw, list) else raw.get("data", [])
    except Exception as e:
        print(f"[Polymarket] fetch error: {e}")
        return []


def fetch_markets(limit: int = 200) -> list[dict]:
    """
    Fetch active markets from Gamma API.
    Makes two calls:
      1. Standard volume-sorted scan (broad market view)
      2. BTC keyword search (targeted for BTC rapid markets)
    Deduplicates by conditionId.
    """
    base = {"active": "true", "closed": "false"}

    raw_all = _gamma_get({**base, "limit": limit})

    # Targeted BTC search — catches rapid BTC price markets
    raw_btc = _gamma_get({**base, "limit": 50, "search": "bitcoin"})
    raw_btc += _gamma_get({**base, "limit": 50, "search": "btc"})

    # Deduplicate by conditionId
    seen: set[str] = set()
    combined: list[dict] = []
    for m in raw_all + raw_btc:
        cid = m.get("conditionId") or m.get("condition_id", "")
        if cid and cid not in seen:
            seen.add(cid)
            combined.append(m)

    if not combined:
        print("[Polymarket] No markets returned")
    return combined


def filter_eligible(markets: list[dict]) -> list[dict]:
    """
    Keep markets with sufficient liquidity/volume.
    BTC short-duration markets (within BTC_SNIPER_MAX_MINUTES) get a separate
    'btc_short' flag so _cycle can apply tighter edge + smaller sizing.
    """
    eligible = []
    for m in markets:
        parsed = parse_market(m)
        if not parsed:
            continue
        if parsed.get("closed"):
            continue

        mins = parsed.get("minutes_to_resolve")
        is_btc = parsed.get("is_btc", False)

        # BTC short-duration tier: relaxed liquidity/volume requirements
        if (BTC_SNIPER_ENABLED and is_btc and mins is not None
                and BTC_SNIPER_MIN_MINUTES <= mins <= BTC_SNIPER_MAX_MINUTES):
            parsed["btc_short"] = True
            eligible.append(parsed)
            continue

        # Standard tier: full liquidity + volume requirements
        if parsed["liquidity"] < MIN_LIQUIDITY:
            continue
        if parsed["volume"] < MIN_VOLUME:
            continue
        parsed["btc_short"] = False
        eligible.append(parsed)

    # BTC short-duration markets first (time-sensitive)
    eligible.sort(key=lambda x: (not x.get("btc_short", False),
                                  x.get("minutes_to_resolve") or 9999))
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
    btc_short_count = sum(1 for m in eligible if m.get("btc_short"))
    print(f"[Sniper] {len(markets)} total → {len(eligible)} eligible "
          f"({btc_short_count} BTC short-duration)")

    fired = 0
    for market in eligible:
        cid = market["condition_id"]
        if state.already_open(cid):
            continue

        is_btc_short = market.get("btc_short", False)
        mins = market.get("minutes_to_resolve")

        # Use BTC-specific edge/sizing for short-duration markets
        min_edge_gate = BTC_SNIPER_MIN_EDGE if is_btc_short else MIN_EDGE
        max_bet_pct   = BTC_SNIPER_MAX_BET_PCT if is_btc_short else kelly.max_position_pct

        # Kelly sizing with the appropriate bankroll cap
        bet = kelly.calculate(
            market_prob=_estimate_true_prob(market),
            market_price=market["yes_price"],
        )
        if bet is None:
            continue

        if bet["edge"] < min_edge_gate:
            continue

        # Apply BTC short-duration bet cap
        if is_btc_short:
            bet["bet_size"] = min(bet["bet_size"], state.bankroll * max_bet_pct)
            bet["bet_size"] = round(bet["bet_size"], 2)

        # Open position
        state.open_position(market, bet)
        fired += 1

        tier_tag = f"⚡ BTC {mins:.0f}min" if is_btc_short else "🎯"
        summary = (
            f"{tier_tag} <b>Polymarket Signal</b>\n"
            f"<b>{market['question'][:80]}</b>\n"
            f"Direction: {bet['direction']}\n"
            f"Edge: {bet['edge']*100:.1f}%  |  Kelly: {bet['kelly_pct']:.1f}%\n"
            f"Bet: ${bet['bet_size']:.2f}  |  Mode: {'PAPER' if PAPER_TRADE_ONLY else 'LIVE'}\n"
            f"Bankroll: ${state.bankroll:.2f}"
        )
        _tg(summary)
        print(f"  {'⚡' if is_btc_short else '✅'} {bet['direction']} | "
              f"${bet['bet_size']:.2f} | edge={bet['edge']*100:.1f}% | "
              f"{market['question'][:60]}")

    if fired == 0:
        print("[Sniper] No edges found this cycle")

    # Write scan results for dashboard
    scan_out = []
    for market in eligible[:50]:
        prob = _estimate_true_prob(market)
        edge = prob - market["yes_price"]
        scan_out.append({
            "question": market["question"][:80],
            "condition_id": market["condition_id"],
            "edge": round(abs(edge), 4),
            "confidence": round(prob, 4),
            "price": market["yes_price"],
            "liquidity": market["liquidity"],
            "volume": market["volume"],
            "is_btc": market.get("is_btc", False),
            "minutes_to_resolve": market.get("minutes_to_resolve"),
        })
    scan_out.sort(key=lambda x: x["edge"], reverse=True)
    try:
        scan_path = DATA_DIR / "scan_results.json"
        scan_path.write_text(json.dumps(scan_out, indent=2))
    except Exception:
        pass


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
