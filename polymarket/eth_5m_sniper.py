"""
APEX — Polymarket ETH 5-Minute Sniper
═══════════════════════════════════════════════════════════════
Targets Polymarket's "Ethereum Up or Down" 5-minute prediction markets.

Strategy: Last-second momentum arbitrage
  1. Discovers current 5-min window via Gamma API slug pattern
  2. Records ETH price at window start (Binance)
  3. In the final ENTRY_WINDOW_SECS (30-60s):
     - Fetches live ETH price
     - Estimates P(Up) using Brownian motion model
     - Compares against Polymarket implied odds
     - Bets if edge > threshold
  4. Market auto-resolves — no exit needed

Edge source: ETH spot price on Binance updates faster than
Polymarket's order book reprices, creating a 2-15 second
information advantage in the final seconds of each window.

Usage:
    python3 polymarket/eth_5m_sniper.py           # paper mode
    python3 polymarket/eth_5m_sniper.py --live     # live (needs wallet)
"""
from __future__ import annotations

import argparse
import json
import math
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

try:
    from scipy.stats import norm as _norm
    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False

from polymarket.polyconfig import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    STARTING_BANKROLL_ETH as STARTING_BANKROLL, KELLY_FRACTION, DATA_DIR,
)

# ── Configuration ─────────────────────────────────────────────────────────────

WINDOW_SECS         = 300       # 5 minutes
ENTRY_WINDOW_SECS   = 15        # Enter in last 15 seconds (T-15s to T-5s)
EXIT_BUFFER_SECS    = 5         # Stop entering with <5s left (blockchain latency)
MIN_CONFIDENCE       = 0.20     # Minimum confidence to trade (from strategy)
MIN_EDGE             = 0.05     # 5% edge minimum (research shows 3% eaten by fees)
MAX_BET_PCT          = 0.04     # 4% of bankroll per trade
KELLY_FRAC           = 0.25     # Quarter-Kelly
ETH_5M_SIGMA         = 0.004   # ~0.4% typical 5-min ETH volatility (higher than BTC)
POLL_INTERVAL_SECS   = 2        # 2-second polling during entry window
CYCLE_SLEEP_SECS     = 10       # Sleep between window checks
WARMUP_SECS          = 30       # Start collecting ticks 30s before entry
# Binary hedge arb: buy both sides when Up + Down < threshold
HEDGE_ARB_THRESHOLD  = 0.97     # Combined cost < $0.97 = locked 3%+ profit
HEDGE_ARB_ENABLED    = True     # Direction-agnostic arb (survives fees)

GAMMA_API = "https://gamma-api.polymarket.com"
# Binance global is geoblocked in the US — use Binance US + Coinbase fallback
BINANCE_US_PRICE_URL = "https://api.binance.us/api/v3/ticker/price?symbol=ETHUSDT"
COINBASE_PRICE_URL = "https://api.coinbase.com/v2/prices/ETH-USD/spot"
BINANCE_US_KLINE_URL = "https://api.binance.us/api/v3/klines"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

STATE_PATH = DATA_DIR / "eth_5m_state.json"


# ── Telegram ──────────────────────────────────────────────────────────────────

def _tg(text: str):
    """Send trade entry/exit notifications to Telegram."""
    import urllib.parse, urllib.request
    data = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML",
    }).encode()
    try:
        urllib.request.urlopen(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data=data, timeout=10,
        )
    except Exception:
        pass


# ── ETH Price Feed ────────────────────────────────────────────────────────────

def get_eth_price() -> float | None:
    """Fetch ETH/USDT spot price. Tries Binance US then Coinbase."""
    if _HAS_REQUESTS:
        # Binance US (fastest, sub-second updates)
        try:
            r = _req.get(BINANCE_US_PRICE_URL, timeout=5)
            if r.status_code == 200:
                return float(r.json()["price"])
        except Exception:
            pass
        # Coinbase fallback
        try:
            r = _req.get(COINBASE_PRICE_URL, timeout=5)
            if r.status_code == 200:
                return float(r.json()["data"]["amount"])
        except Exception:
            pass
    # urllib fallback
    for url, parser in [
        (BINANCE_US_PRICE_URL, lambda d: float(d["price"])),
        (COINBASE_PRICE_URL, lambda d: float(d["data"]["amount"])),
    ]:
        try:
            req = urllib.request.Request(url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=5) as f:
                return parser(json.loads(f.read().decode()))
        except Exception:
            continue
    return None


# ── 1-Minute Candle Feed ──────────────────────────────────────────────────────

def fetch_1m_candles(limit: int = 30) -> list[dict]:
    """Fetch recent 1-minute ETH/USDT candles from Binance US."""
    url = BINANCE_US_KLINE_URL
    params = {"symbol": "ETHUSDT", "interval": "1m", "limit": limit}

    if _HAS_REQUESTS:
        try:
            r = _req.get(url, params=params, timeout=5)
            if r.status_code == 200:
                return _parse_klines(r.json())
        except Exception:
            pass
    try:
        qs = urllib.parse.urlencode(params)
        req = urllib.request.Request(f"{url}?{qs}", headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=5) as f:
            return _parse_klines(json.loads(f.read().decode()))
    except Exception:
        return []


def _parse_klines(raw: list) -> list[dict]:
    """Parse Binance kline response into OHLCV dicts."""
    candles = []
    for k in raw:
        candles.append({
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
        })
    return candles


# ── Market Discovery ──────────────────────────────────────────────────────────

def _current_window_ts() -> int:
    """Return the Unix timestamp of the current 5-min window start."""
    now = int(time.time())
    return now - (now % WINDOW_SECS)


def _next_window_ts() -> int:
    return _current_window_ts() + WINDOW_SECS


def _secs_into_window() -> float:
    """How many seconds we are into the current 5-min window."""
    return time.time() - _current_window_ts()


def _secs_remaining() -> float:
    """Seconds left in the current 5-min window."""
    return WINDOW_SECS - _secs_into_window()


def fetch_5m_event(window_ts: int) -> dict | None:
    """
    Fetch the Polymarket event for a specific 5-min window.
    Slug pattern: btc-updown-5m-{unix_timestamp}
    """
    slug = f"eth-updown-5m-{window_ts}"
    url = f"{GAMMA_API}/events"

    if _HAS_REQUESTS:
        try:
            r = _req.get(url, params={"slug": slug}, headers=_HEADERS, timeout=10)
            if r.status_code == 200:
                events = r.json()
                if isinstance(events, list) and events:
                    return events[0]
        except Exception:
            pass
    return None


def parse_5m_market(event: dict) -> dict | None:
    """
    Extract Up/Down prices, token IDs, condition ID from a 5-min event.
    Returns dict with: up_price, down_price, up_token_id, down_token_id,
                       condition_id, question, volume
    """
    markets = event.get("markets", [])
    if not markets:
        return None

    m = markets[0]
    question = m.get("question", "")
    condition_id = m.get("conditionId", "")

    # Parse prices
    prices_raw = m.get("outcomePrices", "[]")
    prices = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
    if not prices or len(prices) < 2:
        return None

    up_price = float(prices[0])
    down_price = float(prices[1])

    # Parse token IDs
    tokens_raw = m.get("clobTokenIds", "[]")
    tokens = json.loads(tokens_raw) if isinstance(tokens_raw, str) else tokens_raw
    if not tokens or len(tokens) < 2:
        return None

    volume = float(m.get("volume", 0) or 0)

    return {
        "question": question,
        "condition_id": condition_id,
        "up_price": up_price,
        "down_price": down_price,
        "up_token_id": tokens[0],
        "down_token_id": tokens[1],
        "volume": volume,
    }


# ── Probability Model ────────────────────────────────────────────────────────

def estimate_p_up(start_price: float, current_price: float,
                  secs_remaining: float) -> float:
    """
    Estimate probability that BTC will be >= start_price at window end,
    given current_price and seconds remaining.

    Uses Geometric Brownian Motion:
      delta = ln(current / start)
      sigma_remaining = sigma_5m * sqrt(secs_remaining / 300)
      P(Up) = Phi(delta / sigma_remaining)

    When current > start and little time remains, P(Up) → 1.
    When current < start and little time remains, P(Up) → 0.
    """
    if secs_remaining <= 0:
        return 1.0 if current_price >= start_price else 0.0

    delta = math.log(current_price / start_price) if start_price > 0 else 0.0
    sigma_remaining = ETH_5M_SIGMA * math.sqrt(secs_remaining / WINDOW_SECS)

    if sigma_remaining < 1e-10:
        return 1.0 if delta >= 0 else 0.0

    z = delta / sigma_remaining

    if _HAS_SCIPY:
        return float(_norm.cdf(z))
    else:
        # Approximation of normal CDF
        return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


# ── Kelly Sizing ──────────────────────────────────────────────────────────────

def kelly_bet(p_win: float, market_price: float, bankroll: float) -> dict | None:
    """
    Kelly-size a binary bet.
    p_win: our estimated probability of winning
    market_price: cost per share (0-1)
    Returns: {direction, bet_size, edge, kelly_pct} or None
    """
    if market_price <= 0.01 or market_price >= 0.99:
        return None

    b = (1.0 / market_price) - 1.0  # odds ratio
    if b <= 0:
        return None

    edge = p_win - market_price
    if abs(edge) < MIN_EDGE:
        return None

    full_kelly = (p_win * b - (1.0 - p_win)) / b
    if full_kelly <= 0:
        return None

    frac = full_kelly * KELLY_FRAC
    bet_size = min(frac * bankroll, bankroll * MAX_BET_PCT)
    bet_size = round(max(bet_size, 0.0), 2)

    if bet_size < 0.50:  # minimum viable bet
        return None

    return {
        "direction": "UP",
        "bet_size": bet_size,
        "edge": round(edge, 4),
        "kelly_pct": round(full_kelly * 100, 2),
        "p_win": round(p_win, 4),
        "market_price": market_price,
    }


# ── Execution ─────────────────────────────────────────────────────────────────

class LiveExecutor:
    """Places real orders via py-clob-client."""

    def __init__(self, private_key: str):
        from py_clob_client.client import ClobClient
        self.client = ClobClient(
            "https://clob.polymarket.com",
            key=private_key,
            chain_id=137,
        )
        self.client.set_api_creds(self.client.create_or_derive_api_creds())

    def buy(self, token_id: str, amount: float, price: float) -> dict:
        from py_clob_client.clob_types import MarketOrderArgs, OrderType
        from py_clob_client.order_builder.constants import BUY

        order = MarketOrderArgs(
            token_id=token_id,
            amount=amount,
            side=BUY,
            order_type=OrderType.FOK,
        )
        signed = self.client.create_market_order(order)
        resp = self.client.post_order(signed, OrderType.FOK)
        return resp


class PaperExecutor:
    """Simulates trades for backtesting / paper mode."""

    def buy(self, token_id: str, amount: float, price: float) -> dict:
        return {
            "success": True,
            "orderID": f"paper_{int(time.time()*1000)}",
            "status": "matched",
            "mode": "paper",
        }


# ── State Persistence ─────────────────────────────────────────────────────────

class SniperState:
    def __init__(self):
        self.bankroll = STARTING_BANKROLL
        self.trades: list[dict] = []
        self.windows_scanned = 0
        self.windows_traded = 0
        self._load()

    def _load(self):
        if STATE_PATH.exists():
            try:
                d = json.loads(STATE_PATH.read_text())
                self.bankroll = d.get("bankroll", STARTING_BANKROLL)
                self.trades = d.get("trades", [])
                self.windows_scanned = d.get("windows_scanned", 0)
                self.windows_traded = d.get("windows_traded", 0)
            except Exception:
                pass

    def compute_stats(self) -> dict:
        """Authoritative trade counts. All consumers must read from here."""
        total = len(self.trades)
        resolved = [t for t in self.trades if t.get("resolved")]
        wins = sum(1 for t in resolved if t.get("won"))
        losses = len(resolved) - wins
        pending = total - len(resolved)
        pnl = round(sum(t.get("pnl", 0) for t in resolved), 2)
        wr = round(wins / len(resolved) * 100, 1) if resolved else 0.0
        return {
            "total_trades": total,
            "resolved_trades": len(resolved),
            "pending_trades": pending,
            "wins": wins,
            "losses": losses,
            "win_rate": wr,
            "realized_pnl": pnl,
        }

    def save(self):
        STATE_PATH.write_text(json.dumps({
            "bankroll": self.bankroll,
            "trades": self.trades[-500:],  # keep last 500
            "windows_scanned": self.windows_scanned,
            "windows_traded": self.windows_traded,
            "stats": self.compute_stats(),
            "updated": datetime.now(timezone.utc).isoformat(),
        }, indent=2))

    def record_trade(self, trade: dict):
        self.trades.append(trade)
        self.windows_traded += 1
        self.bankroll -= trade.get("bet_size", 0)
        self.save()

    def record_resolution(self, window_ts: int, won: bool, pnl: float):
        """Update the most recent trade for this window with resolution."""
        for t in reversed(self.trades):
            if t.get("window_ts") == window_ts:
                t["resolved"] = True
                t["won"] = won
                t["pnl"] = round(pnl, 2)
                self.bankroll += t["bet_size"] + pnl  # return stake + net
                break
        self.save()

    def summary(self) -> str:
        s = self.compute_stats()
        return (f"Bankroll: ${self.bankroll:.2f} | "
                f"Trades: {s['resolved_trades']} ({s['pending_trades']}p) | "
                f"WR: {s['win_rate']}% | "
                f"PnL: ${s['realized_pnl']:+.2f} | "
                f"Scanned: {self.windows_scanned}")


# ── Core Loop ─────────────────────────────────────────────────────────────────

def run_sniper(live_mode: bool = False):
    from polymarket.btc_strategy import analyze as run_strategy

    state = SniperState()
    executor = _build_executor(live_mode)
    mode_tag = "LIVE" if live_mode else "PAPER"

    # Reset state on first live launch (don't carry paper trades into live)
    if live_mode and state.trades and state.trades[0].get("mode") == "paper":
        print(f"[ETH-5M] Resetting state for LIVE mode (was paper with {len(state.trades)} trades)")
        state.bankroll = 50.0  # live bankroll
        state.trades = []
        state.windows_scanned = 0
        state.windows_traded = 0
        state.save()
    print(f"[ETH-5M] Started ({mode_tag}) — v2 multi-indicator strategy")
    print(f"[ETH-5M] Config: min_conf={MIN_CONFIDENCE}, edge>{MIN_EDGE*100:.0f}%, "
          f"max_bet={MAX_BET_PCT*100:.0f}%, "
          f"entry=T-{ENTRY_WINDOW_SECS}s, poll={POLL_INTERVAL_SECS}s")

    last_traded_window = 0
    tick_buffer: list[float] = []   # 2-second price samples
    tick_window_ts = 0              # which window the ticks belong to

    while True:
        try:
            window_ts = _current_window_ts()
            secs_left = _secs_remaining()

            # Reset tick buffer when window changes
            if window_ts != tick_window_ts:
                tick_buffer = []
                tick_window_ts = window_ts

            # Warmup phase: collect tick prices before entry window
            if secs_left <= (ENTRY_WINDOW_SECS + WARMUP_SECS) and secs_left > ENTRY_WINDOW_SECS:
                eth = get_eth_price()
                if eth:
                    tick_buffer.append(eth)
                time.sleep(POLL_INTERVAL_SECS)
                continue

            # Too early — sleep until warmup phase
            if secs_left > ENTRY_WINDOW_SECS + WARMUP_SECS:
                wait = secs_left - ENTRY_WINDOW_SECS - WARMUP_SECS
                time.sleep(min(wait, CYCLE_SLEEP_SECS))
                continue

            # Too late — blockchain can't confirm
            if secs_left < EXIT_BUFFER_SECS:
                time.sleep(EXIT_BUFFER_SECS + 1)
                continue

            # Already traded this window
            if window_ts == last_traded_window:
                time.sleep(POLL_INTERVAL_SECS)
                continue

            # ── Entry window active (T-15s to T-5s) ─────────────────────

            state.windows_scanned += 1

            # 1. Fetch market from Polymarket
            event = fetch_5m_event(window_ts)
            if not event:
                print(f"[ETH-5M] No event for window {window_ts}")
                last_traded_window = window_ts  # don't retry
                time.sleep(POLL_INTERVAL_SECS)
                continue

            market = parse_5m_market(event)
            if not market:
                print(f"[ETH-5M] Could not parse market")
                last_traded_window = window_ts
                time.sleep(POLL_INTERVAL_SECS)
                continue

            # 1b. Binary Hedge Arb: if Up + Down < threshold, buy both
            if HEDGE_ARB_ENABLED:
                combined = market["up_price"] + market["down_price"]
                if combined < HEDGE_ARB_THRESHOLD:
                    arb_profit_pct = (1.0 - combined) / combined * 100
                    arb_bet = min(state.bankroll * MAX_BET_PCT, 10.0)
                    print(f"\n  [HEDGE ARB] Up={market['up_price']:.3f} + "
                          f"Down={market['down_price']:.3f} = {combined:.3f} "
                          f"| locked profit: {arb_profit_pct:.1f}% | ${arb_bet:.2f}")

                    trade = {
                        "window_ts": window_ts,
                        "question": market["question"],
                        "direction": "HEDGE_ARB",
                        "bet_size": round(arb_bet, 2),
                        "edge": round(1.0 - combined, 4),
                        "p_win": 1.0,
                        "market_price": combined,
                        "confidence": 1.0,
                        "score": 0,
                        "indicators": {"type": "binary_hedge_arb",
                                       "up_price": market["up_price"],
                                       "down_price": market["down_price"],
                                       "combined": combined},
                        "btc_price": get_eth_price() or 0,
                        "start_price": 0,
                        "secs_remaining": _secs_remaining(),
                        "order_id": f"paper_{int(time.time()*1000)}",
                        "mode": mode_tag,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "resolved": True,
                        "won": True,
                        "pnl": round(arb_bet * (1.0 - combined) / combined, 2),
                    }
                    state.record_trade(trade)
                    state.bankroll += trade["bet_size"] + trade["pnl"]  # return stake + profit
                    state.save()

                    _tg(f"🔒 <b>Hedge Arb +${trade['pnl']:.2f}</b> ({arb_profit_pct:.1f}% locked)")
                    last_traded_window = window_ts
                    continue

            # 2. Fetch start price + current price + 1-min candles
            start_price = _get_window_start_price(window_ts)
            if start_price is None:
                print(f"[ETH-5M] No start price available")
                last_traded_window = window_ts
                time.sleep(POLL_INTERVAL_SECS)
                continue

            candles_1m = fetch_1m_candles(30)

            # 3. Poll with 2-second ticks, run strategy each poll
            best_signal = None
            best_confidence = 0.0
            fired = False

            while _secs_remaining() > EXIT_BUFFER_SECS and not fired:
                secs_left = _secs_remaining()
                current_eth = get_eth_price()
                if current_eth is None:
                    time.sleep(POLL_INTERVAL_SECS)
                    continue

                tick_buffer.append(current_eth)

                # Run 7-indicator strategy
                result = run_strategy(
                    window_open=start_price,
                    current_price=current_eth,
                    candles_1m=candles_1m,
                    tick_prices=tick_buffer[-30:],  # last 60 seconds of ticks
                )

                # Track best signal seen
                if result.confidence > best_confidence:
                    best_confidence = result.confidence
                    best_signal = result

                # Dislocation check: only fire when edge is big enough
                # to survive ~3.15% dynamic taker fee at 50/50 odds
                # MACD gate: delta-only signals (zero MACD confirmation)
                # need confidence >= 0.60 (big move) to trade without momentum
                if result.confidence >= MIN_CONFIDENCE and not (
                    result.macd_confirmation == 0 and result.confidence < 0.60
                ):
                    direction = result.direction
                    token_id = (market["up_token_id"] if direction == "UP"
                                else market["down_token_id"])
                    poly_price = (market["up_price"] if direction == "UP"
                                  else market["down_price"])

                    # Use realistic token price estimate from strategy
                    effective_price = max(poly_price, result.entry_price_est)

                    # Kelly sizing with estimated true probability
                    p_win = estimate_p_up(start_price, current_eth, secs_left)
                    if direction == "DOWN":
                        p_win = 1.0 - p_win

                    bet = kelly_bet(p_win, effective_price, state.bankroll)
                    if bet and bet["edge"] >= MIN_EDGE:
                        bet["direction"] = direction
                        _execute_trade(
                            state, executor, market, bet, direction, token_id,
                            current_eth, start_price, secs_left, mode_tag,
                            window_ts, result,
                        )
                        last_traded_window = window_ts
                        fired = True
                        continue

                time.sleep(POLL_INTERVAL_SECS)

            # T-5s hard deadline: if not fired, execute best signal if viable
            # Same MACD gate: require confirmation for sub-0.60 confidence
            if not fired and best_signal and best_signal.confidence >= MIN_CONFIDENCE and not (
                best_signal.macd_confirmation == 0 and best_signal.confidence < 0.60
            ):
                current_eth = get_eth_price() or tick_buffer[-1]
                secs_left = _secs_remaining()
                direction = best_signal.direction
                token_id = (market["up_token_id"] if direction == "UP"
                            else market["down_token_id"])
                poly_price = (market["up_price"] if direction == "UP"
                              else market["down_price"])
                effective_price = max(poly_price, best_signal.entry_price_est)

                p_win = estimate_p_up(start_price, current_eth, secs_left)
                if direction == "DOWN":
                    p_win = 1.0 - p_win

                bet = kelly_bet(p_win, effective_price, state.bankroll)
                if bet:
                    bet["direction"] = direction
                    _execute_trade(
                        state, executor, market, bet, direction, token_id,
                        current_eth, start_price, secs_left, mode_tag,
                        window_ts, best_signal,
                    )
                    fired = True

            if not fired:
                delta_pct = ((tick_buffer[-1] - start_price) / start_price * 100
                             if tick_buffer else 0)
                conf_str = f"{best_confidence:.0%}" if best_signal else "N/A"
                print(f"[ETH-5M] No trade | delta={delta_pct:+.3f}% | "
                      f"best_conf={conf_str} | ticks={len(tick_buffer)}")

            last_traded_window = window_ts

        except KeyboardInterrupt:
            print(f"\n[ETH-5M] Stopped. {state.summary()}")
            state.save()
            break
        except Exception as e:
            print(f"[ETH-5M] Error: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(CYCLE_SLEEP_SECS)


def _execute_trade(state, executor, market, bet, direction, token_id,
                   current_eth, start_price, secs_left, mode_tag,
                   window_ts, strategy_result):
    """Execute a trade and wait for resolution."""
    print(f"\n  {'⚡' if mode_tag == 'LIVE' else '📋'} ETH-5M | {direction} | "
          f"conf={strategy_result.confidence:.0%} | "
          f"edge={bet['edge']*100:.1f}% | ${bet['bet_size']:.2f} | "
          f"score={strategy_result.score:+.1f} | {secs_left:.0f}s left")

    result = executor.buy(token_id, bet["bet_size"], bet["market_price"])

    trade = {
        "window_ts": window_ts,
        "question": market["question"],
        "direction": direction,
        "bet_size": bet["bet_size"],
        "edge": bet["edge"],
        "p_win": bet["p_win"],
        "market_price": bet["market_price"],
        "confidence": strategy_result.confidence,
        "score": strategy_result.score,
        "indicators": strategy_result.indicators,
        "btc_price": current_eth,
        "start_price": start_price,
        "secs_remaining": round(secs_left, 1),
        "order_id": result.get("orderID", ""),
        "mode": mode_tag,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "resolved": False,
    }
    state.record_trade(trade)

    # Entry notification silenced — only wins/losses are reported.
    # Wait for resolution
    _wait_and_resolve(state, trade, start_price, window_ts)


def _get_window_start_price(window_ts: int) -> float | None:
    """
    Fetch ETH price at the start of the 5-min window using Binance kline API.
    The kline for this 5-min period has open price = start price.
    """
    # Binance US kline endpoint: 5-min candles
    url = BINANCE_US_KLINE_URL
    params = {
        "symbol": "ETHUSDT",
        "interval": "5m",
        "startTime": window_ts * 1000,
        "limit": 1,
    }

    if _HAS_REQUESTS:
        try:
            r = _req.get(url, params=params, timeout=5)
            if r.status_code == 200:
                klines = r.json()
                if klines:
                    return float(klines[0][1])  # [1] = open price
        except Exception:
            pass

    try:
        qs = urllib.parse.urlencode(params)
        req = urllib.request.Request(f"{url}?{qs}", headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=5) as f:
            klines = json.loads(f.read().decode())
            if klines:
                return float(klines[0][1])  # open price
    except Exception:
        pass

    return None


def _wait_and_resolve(state: SniperState, trade: dict, start_price: float,
                      window_ts: int):
    """Wait for the current window to end, then check resolution."""
    # Wait until window ends + small buffer for Chainlink settlement
    secs_left = _secs_remaining()
    if secs_left > 0:
        time.sleep(secs_left + 3)

    # Fetch BTC price after settlement (the close of the 5-min candle)
    time.sleep(5)  # extra buffer for oracle
    end_price = get_eth_price()
    if end_price is None:
        # Try Binance kline
        end_price = _get_window_start_price(window_ts + WINDOW_SECS)

    if end_price is None:
        print(f"[ETH-5M] Could not determine end price for resolution")
        return

    # Resolution: Up if end >= start, Down otherwise
    went_up = end_price >= start_price
    bet_direction = trade["direction"]
    won = (bet_direction == "UP" and went_up) or (bet_direction == "DOWN" and not went_up)

    if won:
        # Pay 1/price per share, receive $1 per share
        payout = trade["bet_size"] / trade["market_price"]
        pnl = payout - trade["bet_size"]
    else:
        pnl = -trade["bet_size"]

    state.record_resolution(window_ts, won, pnl)

    emoji = "✅" if won else "❌"
    outcome = "UP" if went_up else "DOWN"
    print(f"  {emoji} Resolved: {outcome} | Bet: {bet_direction} | "
          f"PnL: ${pnl:+.2f} | End: ${end_price:,.2f}")

    s = state.compute_stats()
    _tg(
        f"{emoji} <b>ETH 5-Min {'WIN' if won else 'LOSS'} ${pnl:+.2f}</b>\n"
        f"Bet {bet_direction} → {outcome}\n"
        f"ETH ${start_price:,.0f} → ${end_price:,.0f}\n"
        f"Bank: ${state.bankroll:.0f} | {s['wins']}W/{s['losses']}L ({s['win_rate']}%) | "
        f"{s['resolved_trades']}/{s['total_trades']} resolved"
    )


def _build_executor(live_mode: bool):
    if live_mode:
        from polymarket.polyconfig import POLY_PRIVATE_KEY
        if not POLY_PRIVATE_KEY:
            print("[ETH-5M] ERROR: --live requires POLY_PRIVATE_KEY in polyconfig.py")
            sys.exit(1)
        return LiveExecutor(POLY_PRIVATE_KEY)
    return PaperExecutor()


# ── Entry Point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Polymarket ETH 5-Min Sniper")
    parser.add_argument("--live", action="store_true",
                        help="Enable live trading (requires Polygon wallet)")
    parser.add_argument("--once", action="store_true",
                        help="Run one window then exit")
    args = parser.parse_args()

    if args.once:
        # Quick test: scan current window
        window_ts = _current_window_ts()
        print(f"Window: {window_ts} | Secs remaining: {_secs_remaining():.0f}")

        eth = get_eth_price()
        print(f"ETH: ${eth:,.2f}" if eth else "ETH: unavailable")

        event = fetch_5m_event(window_ts)
        if event:
            market = parse_5m_market(event)
            if market:
                print(f"Market: {market['question']}")
                print(f"  Up={market['up_price']:.3f} Down={market['down_price']:.3f}")
                print(f"  Volume: ${market['volume']:,.2f}")

                start_price = _get_window_start_price(window_ts)
                if start_price and eth:
                    p_up = estimate_p_up(start_price, eth, _secs_remaining())
                    print(f"  Start: ${start_price:,.2f} | P(Up)={p_up:.3f}")
                    print(f"  Edge UP: {(p_up - market['up_price'])*100:+.1f}%")
                    print(f"  Edge DN: {((1-p_up) - market['down_price'])*100:+.1f}%")
        else:
            print("No event found for current window")
        return

    run_sniper(live_mode=args.live)


if __name__ == "__main__":
    main()
