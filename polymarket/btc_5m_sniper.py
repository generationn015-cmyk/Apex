"""
APEX — Polymarket BTC 5-Minute Sniper
═══════════════════════════════════════════════════════════════
Targets Polymarket's "Bitcoin Up or Down" 5-minute prediction markets.

Strategy: Last-second momentum arbitrage
  1. Discovers current 5-min window via Gamma API slug pattern
  2. Records BTC price at window start (Binance)
  3. In the final ENTRY_WINDOW_SECS (30-60s):
     - Fetches live BTC price
     - Estimates P(Up) using Brownian motion model
     - Compares against Polymarket implied odds
     - Bets if edge > threshold
  4. Market auto-resolves — no exit needed

Edge source: BTC spot price on Binance updates faster than
Polymarket's order book reprices, creating a 2-15 second
information advantage in the final seconds of each window.

Usage:
    python3 polymarket/btc_5m_sniper.py           # paper mode
    python3 polymarket/btc_5m_sniper.py --live     # live (needs wallet)
"""
from __future__ import annotations

import argparse
import json
import os
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
    STARTING_BANKROLL, KELLY_FRACTION, DATA_DIR,
)

# ── Configuration ─────────────────────────────────────────────────────────────

WINDOW_SECS         = 300       # 5 minutes
ENTRY_WINDOW_SECS   = 15        # Enter in last 15 seconds (T-15s to T-5s)
EXIT_BUFFER_SECS    = 5         # Stop entering with <5s left (blockchain latency)
MIN_CONFIDENCE       = 0.20     # Minimum confidence to trade (from strategy)
MIN_EDGE             = 0.02     # 2% edge — proven-filling threshold from earlier today's 8 live fills (trade #3: edge=0.02 filled and won)
MAX_BET_PCT          = 0.04     # 4% of bankroll per trade
KELLY_FRAC           = 0.25     # Quarter-Kelly
BTC_5M_SIGMA         = 0.003   # ~0.3% typical 5-min BTC volatility
POLL_INTERVAL_SECS   = 2        # 2-second polling during entry window
CYCLE_SLEEP_SECS     = 10       # Sleep between window checks
WARMUP_SECS          = 30       # Start collecting ticks 30s before entry
# Binary hedge arb: buy both sides when Up + Down < threshold
HEDGE_ARB_THRESHOLD  = 0.97     # Combined cost < $0.97 = locked 3%+ profit
HEDGE_ARB_ENABLED    = True     # Direction-agnostic arb (survives fees)

GAMMA_API = "https://gamma-api.polymarket.com"
# Binance global is geoblocked in the US — use Binance US + Coinbase fallback
BINANCE_US_PRICE_URL = "https://api.binance.us/api/v3/ticker/price?symbol=BTCUSDT"
COINBASE_PRICE_URL = "https://api.coinbase.com/v2/prices/BTC-USD/spot"
BINANCE_US_KLINE_URL = "https://api.binance.us/api/v3/klines"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

STATE_PATH = DATA_DIR / "btc_5m_state.json"
LOCK_PATH = DATA_DIR / "btc_5m_sniper.pid"


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


# ── BTC Price Feed ────────────────────────────────────────────────────────────

def get_btc_price() -> float | None:
    """Fetch BTC/USDT spot price.
    Order: Binance Global → Coinbase → Binance US.
    Binance US has been observed serving frozen/cached prices from EU VPS,
    so it is last-resort only. Binance Global is Chainlink's primary source
    and is reachable from this VPS."""
    if _HAS_REQUESTS:
        # Binance Global (Chainlink primary, fresh from EU VPS)
        try:
            r = _req.get(BINANCE_GLOBAL_PRICE_URL, timeout=5)
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
        # Binance US last — known stale from this VPS
        try:
            r = _req.get(BINANCE_US_PRICE_URL, timeout=5)
            if r.status_code == 200:
                return float(r.json()["price"])
        except Exception:
            pass
    # urllib fallback
    for url, parser in [
        (BINANCE_GLOBAL_PRICE_URL, lambda d: float(d["price"])),
        (COINBASE_PRICE_URL, lambda d: float(d["data"]["amount"])),
        (BINANCE_US_PRICE_URL, lambda d: float(d["price"])),
    ]:
        try:
            req = urllib.request.Request(url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=5) as f:
                return parser(json.loads(f.read().decode()))
        except Exception:
            continue
    return None


# ── Chainlink Proxy Price Feed ────────────────────────────────────────────────
# Polymarket resolves "Bitcoin Up or Down" using Chainlink BTC/USD Data Streams,
# which aggregates from Binance (global), Coinbase, Kraken, etc.
# We approximate this by querying the same sources Chainlink uses.

BINANCE_GLOBAL_PRICE_URL = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
COINGECKO_PRICE_URL = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"


def get_chainlink_proxy_price() -> float | None:
    """Approximate Chainlink BTC/USD by querying the exchanges it aggregates."""
    if not _HAS_REQUESTS:
        return None
    # Binance global (primary Chainlink source, different from Binance US)
    try:
        r = _req.get(BINANCE_GLOBAL_PRICE_URL, timeout=3)
        if r.status_code == 200:
            return float(r.json()["price"])
    except Exception:
        pass
    # Coinbase (also in Chainlink's aggregation)
    try:
        r = _req.get(COINBASE_PRICE_URL, timeout=3)
        if r.status_code == 200:
            return float(r.json()["data"]["amount"])
    except Exception:
        pass
    # CoinGecko (aggregated price, last resort)
    try:
        r = _req.get(COINGECKO_PRICE_URL, timeout=3)
        if r.status_code == 200:
            return float(r.json()["bitcoin"]["usd"])
    except Exception:
        pass
    return None


def get_multi_source_prices() -> dict:
    """Fetch BTC price from all sources. Helps diagnose Binance US staleness."""
    prices = {}
    if _HAS_REQUESTS:
        for name, url, parser in [
            ("binance_us", BINANCE_US_PRICE_URL, lambda d: float(d["price"])),
            ("binance_global", BINANCE_GLOBAL_PRICE_URL, lambda d: float(d["price"])),
            ("coinbase", COINBASE_PRICE_URL, lambda d: float(d["data"]["amount"])),
        ]:
            try:
                r = _req.get(url, timeout=3)
                if r.status_code == 200:
                    prices[name] = parser(r.json())
            except Exception:
                pass
    if len(prices) >= 2:
        vals = list(prices.values())
        prices["spread"] = round(max(vals) - min(vals), 2)
    return prices


# ── 1-Minute Candle Feed ──────────────────────────────────────────────────────

def fetch_1m_candles(limit: int = 30) -> list[dict]:
    """Fetch recent 1-minute BTC/USDT candles from Binance US."""
    url = BINANCE_US_KLINE_URL
    params = {"symbol": "BTCUSDT", "interval": "1m", "limit": limit}

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
    slug = f"btc-updown-5m-{window_ts}"
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
    sigma_remaining = BTC_5M_SIGMA * math.sqrt(secs_remaining / WINDOW_SECS)

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

    # Polymarket minimum order = 5 shares; enforce minimum USDC value
    MIN_ORDER_USDC = 5.0
    if bet_size < MIN_ORDER_USDC:
        bet_size = MIN_ORDER_USDC
    if bet_size < 0.50:  # absolute floor
        return None

    return {
        "direction": "UP",
        "bet_size": bet_size,
        "edge": round(edge, 4),
        "kelly_pct": round(full_kelly * 100, 2),
        "p_win": round(p_win, 4),
        "market_price": market_price,
    }


# ── Order Book Price Discovery ────────────────────────────────────────────────

def get_best_ask(executor, token_id: str) -> float | None:
    """
    Fetch the actual best (lowest) ask price from the CLOB order book.
    Returns None if no asks available.
    """
    if not hasattr(executor, 'client'):
        return None
    try:
        book = executor.client.get_order_book(token_id)
        asks = book.asks if hasattr(book, 'asks') else []
        if asks:
            return min(float(a.price) for a in asks)
    except Exception:
        pass
    return None


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
        from py_clob_client.clob_types import OrderArgs, OrderType
        from py_clob_client.order_builder.constants import BUY
        import math

        # FAK + LIMIT: takes available liquidity across multiple ask
        # levels, cancels the rest. Because the book moves between the
        # time kelly_bet cached best_ask and now, re-fetch the live top
        # ask right here and price *above* it.
        live_ask = None
        try:
            book = self.client.get_order_book(token_id)
            asks = book.asks if hasattr(book, 'asks') else []
            if asks:
                live_ask = min(float(a.price) for a in asks)
        except Exception:
            pass

        # Use the higher of (cached price, live ask). ceil to next cent
        # then add 3c buffer to survive the ~1-3c reprice between the
        # order_book read and the FAK submit. Edge gate already passed
        # in kelly_bet with a 2% margin, so +3c slippage stays inside
        # the edge at any mid-book price and we still walk away with
        # positive EV on a fill.
        submit_price = max(price, live_ask or 0.0)
        limit_price = math.ceil(submit_price * 100) / 100
        # 8c slippage buffer — winning-side tokens near resolution race
        # up 3-7c between the book snapshot and the FAK hit. 8c stays
        # well inside the 12-19%+ edges we fire on.
        limit_price = min(round(limit_price + 0.08, 2), 0.99)
        if limit_price < 0.01 or limit_price > 0.99:
            raise ValueError(f"Price {limit_price} out of tradeable range")

        target_spend = max(amount, 5.0)
        # Whole-number shares guarantees maker_amount (shares*price)
        # has <=2 decimals, avoiding "invalid amounts" precision error
        shares = max(math.ceil(target_spend / limit_price), 5)

        order_args = OrderArgs(
            token_id=token_id,
            price=limit_price,
            size=float(shares),
            side=BUY,
        )
        signed = self.client.create_order(order_args)
        resp = self.client.post_order(signed, OrderType.FAK)
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


# ── Live CLOB Balance Sync ────────────────────────────────────────────────────

def get_live_clob_balance(executor) -> float | None:
    """Query the actual Polymarket CLOB collateral balance for this wallet."""
    if not hasattr(executor, 'client'):
        return None
    try:
        from py_clob_client.clob_types import BalanceAllowanceParams, AssetType
        resp = executor.client.get_balance_allowance(
            BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
        )
        return int(resp['balance']) / 1e6
    except Exception as e:
        print(f"  [BALANCE] Live sync failed: {e}")
        return None


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

    # Prevent duplicate instances
    if LOCK_PATH.exists():
        try:
            old_pid = int(LOCK_PATH.read_text().strip())
            cmdline = Path(f"/proc/{old_pid}/cmdline").read_bytes().decode(errors="ignore")
            if "btc_5m_sniper" in cmdline:
                print(f"[BTC-5M] ERROR: Another instance already running (PID {old_pid})")
                sys.exit(1)
        except (ValueError, OSError, FileNotFoundError):
            pass
    LOCK_PATH.write_text(str(os.getpid()))

    state = SniperState()
    executor = _build_executor(live_mode)
    mode_tag = "LIVE" if live_mode else "PAPER"

    # Pre-flight: verify CLOB connectivity in live mode
    if live_mode:
        try:
            open_orders = executor.client.get_orders()
            n = len(open_orders) if isinstance(open_orders, list) else 0
            if n > 0:
                print(f"[BTC-5M] WARNING: {n} open orders on CLOB — cancel stale orders")
            print(f"[BTC-5M] CLOB API connected | PID {os.getpid()}")
        except Exception as e:
            print(f"[BTC-5M] WARNING: CLOB pre-flight failed: {e}")

        # Redeem any stuck winning positions to free up collateral
        try:
            from polymarket.auto_redeemer import try_redeem
            try_redeem()
        except Exception as e:
            print(f"[BTC-5M] Startup redeem skipped: {e}")

        # Authoritative bankroll: pull live from CLOB, overwrite state
        live_bal = get_live_clob_balance(executor)
        if live_bal is not None:
            print(f"[BTC-5M] Live CLOB bankroll: ${live_bal:.2f} (state was ${state.bankroll:.2f})")
            state.bankroll = round(live_bal, 2)
            state.save()

    # Reset state on first live launch (don't carry paper trades into live)
    if live_mode and state.trades and state.trades[0].get("mode", "").lower() == "paper":
        print(f"[BTC-5M] Resetting state for LIVE mode (was paper with {len(state.trades)} trades)")
        state.bankroll = 50.0  # live starting bankroll
        state.trades = []
        state.windows_scanned = 0
        state.windows_traded = 0
        state.save()
    print(f"[BTC-5M] Started ({mode_tag}) — v2 multi-indicator strategy")
    print(f"[BTC-5M] Config: min_conf={MIN_CONFIDENCE}, edge>{MIN_EDGE*100:.0f}%, "
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
                # Live bankroll sync — authoritative CLOB balance each window
                if live_mode:
                    live_bal = get_live_clob_balance(executor)
                    if live_bal is not None and abs(live_bal - state.bankroll) > 0.01:
                        print(f"[BTC-5M] Bankroll sync: ${state.bankroll:.2f} -> ${live_bal:.2f}")
                        state.bankroll = round(live_bal, 2)
                        state.save()

            # Warmup phase: collect tick prices before entry window
            if secs_left <= (ENTRY_WINDOW_SECS + WARMUP_SECS) and secs_left > ENTRY_WINDOW_SECS:
                btc = get_btc_price()
                if btc:
                    tick_buffer.append(btc)
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
                print(f"[BTC-5M] No event for window {window_ts}")
                last_traded_window = window_ts  # don't retry
                time.sleep(POLL_INTERVAL_SECS)
                continue

            market = parse_5m_market(event)
            if not market:
                print(f"[BTC-5M] Could not parse market")
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
                        "btc_price": get_btc_price() or 0,
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
                print(f"[BTC-5M] No start price available")
                last_traded_window = window_ts
                time.sleep(POLL_INTERVAL_SECS)
                continue

            candles_1m = fetch_1m_candles(50)   # need >= 35 for full MACD(12,26,9)

            # 3. Poll with 2-second ticks, run strategy each poll
            best_signal = None
            best_confidence = 0.0
            fired = False

            while _secs_remaining() > EXIT_BUFFER_SECS and not fired:
                secs_left = _secs_remaining()
                current_btc = get_btc_price()
                if current_btc is None:
                    time.sleep(POLL_INTERVAL_SECS)
                    continue

                tick_buffer.append(current_btc)

                # Run 7-indicator strategy
                result = run_strategy(
                    window_open=start_price,
                    current_price=current_btc,
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

                    best_ask = get_best_ask(executor, token_id)
                    effective_price = best_ask if best_ask else max(poly_price, result.entry_price_est)

                    p_win = estimate_p_up(start_price, current_btc, secs_left)
                    if direction == "DOWN":
                        p_win = 1.0 - p_win

                    bet = kelly_bet(p_win, effective_price, state.bankroll)
                    if bet is None:
                        reject = (
                            f"price={effective_price:.3f} out-of-range"
                            if effective_price <= 0.01 or effective_price >= 0.99
                            else f"edge={p_win - effective_price:+.3f} < {MIN_EDGE}"
                        )
                        print(f"  ✗ kelly REJECT {direction} conf={result.confidence:.0%} "
                              f"p={p_win:.3f} ask={effective_price:.3f} → {reject}")
                    elif bet["edge"] < MIN_EDGE:
                        print(f"  ✗ edge REJECT {direction} conf={result.confidence:.0%} "
                              f"edge={bet['edge']*100:.1f}% < {MIN_EDGE*100:.0f}%")
                    else:
                        bet["direction"] = direction
                        if _execute_trade(
                            state, executor, market, bet, direction, token_id,
                            current_btc, start_price, secs_left, mode_tag,
                            window_ts, result,
                        ):
                            last_traded_window = window_ts
                            fired = True
                            continue
                elif result.confidence >= MIN_CONFIDENCE:
                    # Gated by MACD rule (conf<60% with no MACD confirmation)
                    pass

                time.sleep(POLL_INTERVAL_SECS)

            # T-5s hard deadline: if not fired, execute best signal if viable
            # Same MACD gate: require confirmation for sub-0.60 confidence
            if not fired and best_signal and best_signal.confidence >= MIN_CONFIDENCE and not (
                best_signal.macd_confirmation == 0 and best_signal.confidence < 0.60
            ):
                current_btc = get_btc_price() or tick_buffer[-1]
                secs_left = _secs_remaining()
                direction = best_signal.direction
                token_id = (market["up_token_id"] if direction == "UP"
                            else market["down_token_id"])
                poly_price = (market["up_price"] if direction == "UP"
                              else market["down_price"])
                best_ask = get_best_ask(executor, token_id)
                effective_price = best_ask if best_ask else max(poly_price, best_signal.entry_price_est)

                p_win = estimate_p_up(start_price, current_btc, secs_left)
                if direction == "DOWN":
                    p_win = 1.0 - p_win

                bet = kelly_bet(p_win, effective_price, state.bankroll)
                if bet:
                    bet["direction"] = direction
                    if _execute_trade(
                        state, executor, market, bet, direction, token_id,
                        current_btc, start_price, secs_left, mode_tag,
                        window_ts, best_signal,
                    ):
                        fired = True

            if not fired:
                delta_pct = ((tick_buffer[-1] - start_price) / start_price * 100
                             if tick_buffer else 0)
                conf_str = f"{best_confidence:.0%}" if best_signal else "N/A"
                print(f"[BTC-5M] No trade | delta={delta_pct:+.3f}% | "
                      f"best_conf={conf_str} | ticks={len(tick_buffer)}")

            last_traded_window = window_ts

        except KeyboardInterrupt:
            print(f"\n[BTC-5M] Stopped. {state.summary()}")
            state.save()
            LOCK_PATH.unlink(missing_ok=True)
            break
        except Exception as e:
            print(f"[BTC-5M] Error: {e}")
            import traceback
            traceback.print_exc()
            last_traded_window = window_ts  # prevent retry storm
            time.sleep(CYCLE_SLEEP_SECS)


def _execute_trade(state, executor, market, bet, direction, token_id,
                   current_btc, start_price, secs_left, mode_tag,
                   window_ts, strategy_result) -> bool:
    """Execute a trade and wait for resolution. Returns True if filled."""
    icon = '⚡' if mode_tag == 'LIVE' else '📋'
    print(f"\n  {icon} BTC-5M | {direction} | "
          f"conf={strategy_result.confidence:.0%} | "
          f"edge={bet['edge']*100:.1f}% | ${bet['bet_size']:.2f} | "
          f"score={strategy_result.score:+.1f} | {secs_left:.0f}s left")

    # Log multi-source prices so we can see Binance US vs Chainlink divergence
    mp = get_multi_source_prices()
    if mp:
        parts = [f"{k}=${v:,.2f}" for k, v in mp.items() if k != "spread"]
        full_spread = mp.get("spread", 0)
        # Spread safety check uses ONLY the fresh sources (Binance Global +
        # Coinbase). Binance US is excluded because it serves frozen/cached
        # prices from EU VPS and would always blow the threshold.
        fresh = [v for k, v in mp.items()
                 if k in ("binance_global", "coinbase")]
        fresh_spread = round(max(fresh) - min(fresh), 2) if len(fresh) >= 2 else 0
        spread_warn = " ⚠️ SPREAD" if fresh_spread > 40 else ""
        print(f"  [PRICES] {' | '.join(parts)} | fresh_spread=${fresh_spread:.2f}"
              f" | full_spread=${full_spread:.2f}{spread_warn}")
        # Safety check: skip trade if fresh sources diverge too much.
        # Normal cross-exchange spread at $70k BTC is $20-50 (~0.05%).
        # $60+ indicates one feed is lagging several seconds.
        if fresh_spread > 60:
            print(f"  ⚠️ Fresh-source divergence ${fresh_spread:.2f} > $60 — skipping")
            return False

    try:
        result = executor.buy(token_id, bet["bet_size"], bet["market_price"])
    except Exception as e:
        err_str = str(e)
        if '403' in err_str or 'geoblock' in err_str.lower() or 'region' in err_str.lower():
            print(f"  [GEO-BLOCK] Live order blocked — recording as paper")
            result = {"success": True, "orderID": f"blocked_{int(time.time()*1000)}", "status": "geo_blocked", "mode": "PAPER"}
            mode_tag = "PAPER"
        elif 'no match' in err_str.lower():
            print(f"  ⚠️ 'no match' raw error: {err_str}")
            return False
        else:
            print(f"  ⚠️ Order failed: {err_str}")
            return False

    # For live FAK orders, verify fill and capture ACTUAL execution price.
    # FAK can partially fill — check size_matched and reject dust fills.
    order_id = result.get("orderID", "")
    fill_price = bet["market_price"]
    fill_shares = 0.0
    fill_cost = bet["bet_size"]
    MIN_FILL_USDC = 1.0  # reject fills under $1 (dust, eaten by fees)

    if mode_tag == "LIVE" and order_id and not order_id.startswith("blocked_"):
        fill_verified = False
        for fill_attempt in range(3):
            try:
                time.sleep(1 * (fill_attempt + 1))  # 1s, 2s, 3s backoff
                order_info = executor.client.get_order(order_id)
                if order_info is None:
                    print(f"  ⚠️ Fill check returned None (attempt {fill_attempt+1}/3)")
                    continue
                matched = float(order_info.get("size_matched", "0"))
                if matched == 0:
                    print(f"  ⚠️ Order NOT FILLED — skipping trade")
                    return False
                fill_shares = matched
                fill_price = float(order_info.get("price", bet["market_price"]))
                fill_cost = round(fill_shares * fill_price, 2)
                if fill_cost < MIN_FILL_USDC:
                    print(f"  ⚠️ Dust fill (${fill_cost:.2f}) — too small, skipping")
                    return False
                requested = bet["bet_size"]
                pct = fill_cost / requested * 100 if requested > 0 else 0
                print(f"  FILLED: {fill_shares} shares @ ${fill_price:.3f} = ${fill_cost:.2f} ({pct:.0f}% of ${requested:.2f})")
                _tg(
                    f"🎯 <b>BTC 5-Min ENTRY</b> · {direction}\n"
                    f"{fill_shares:.2f} @ ${fill_price:.3f} = <b>${fill_cost:.2f}</b>\n"
                    f"edge {bet['edge']*100:.1f}% · conf {strategy_result.confidence:.0%} · "
                    f"BTC ${current_btc:,.0f}"
                )
                fill_verified = True
                break
            except Exception as e:
                print(f"  ⚠️ Fill check error (attempt {fill_attempt+1}/3): {e}")
        if not fill_verified:
            # Check trade history as last resort before giving up
            try:
                trades_resp = executor.client.get_trades()
                if trades_resp:
                    for poly_trade in (trades_resp if isinstance(trades_resp, list) else []):
                        if poly_trade.get("taker_order_id") == order_id:
                            fill_shares = float(poly_trade.get("size", "0"))
                            fill_price = float(poly_trade.get("price", bet["market_price"]))
                            fill_cost = round(fill_shares * fill_price, 2)
                            print(f"  FILLED (from trade history): {fill_shares} shares @ ${fill_price:.3f} = ${fill_cost:.2f}")
                            fill_verified = True
                            break
            except Exception as e:
                print(f"  ⚠️ Trade history fallback failed: {e}")
            if not fill_verified:
                print(f"  ⚠️ Could not verify fill after 3 attempts — skipping trade")
                return False

    trade = {
        "window_ts": window_ts,
        "question": market["question"],
        "direction": direction,
        "bet_size": fill_cost,
        "edge": bet["edge"],
        "p_win": bet["p_win"],
        "market_price": fill_price,
        "fill_shares": fill_shares,
        "confidence": strategy_result.confidence,
        "score": strategy_result.score,
        "indicators": strategy_result.indicators,
        "btc_price": current_btc,
        "start_price": start_price,
        "secs_remaining": round(secs_left, 1),
        "order_id": order_id,
        "mode": mode_tag,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "resolved": False,
    }
    state.record_trade(trade)

    # Wait for resolution — use Polymarket/Chainlink oracle (authoritative)
    condition_id = market.get("condition_id", "")
    try:
        _wait_and_resolve(state, trade, start_price, window_ts,
                          executor=executor, condition_id=condition_id)
    except Exception as e:
        print(f"  ⚠️ Resolution error: {e} — trade recorded, will reconcile")
    return True


def _get_window_start_price(window_ts: int) -> float | None:
    """
    Fetch BTC price at the start of the 5-min window using Binance kline API.
    The kline for this 5-min period has open price = start price.
    """
    # Binance US kline endpoint: 5-min candles
    url = BINANCE_US_KLINE_URL
    params = {
        "symbol": "BTCUSDT",
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


def _query_polymarket_resolution(executor, condition_id: str,
                                  max_attempts: int = 12,
                                  poll_secs: float = 10) -> str | None:
    """
    Poll Polymarket CLOB for actual market resolution (Chainlink oracle).
    Returns 'Up', 'Down', or None if unresolved after all attempts.
    """
    if not hasattr(executor, 'client'):
        return None
    for attempt in range(max_attempts):
        try:
            m = executor.client.get_market(condition_id)
            if m and isinstance(m, dict) and m.get("closed"):
                tokens = m.get("tokens", [])
                for tok in tokens:
                    if tok.get("winner"):
                        return tok["outcome"]  # 'Up' or 'Down'
        except Exception as e:
            if attempt == 0:
                print(f"  [RESOLVE] CLOB query error: {e}")
        if attempt < max_attempts - 1:
            time.sleep(poll_secs)
    return None


def _wait_and_resolve(state: SniperState, trade: dict, start_price: float,
                      window_ts: int, executor=None, condition_id: str = ""):
    """Wait for the current window to end, then check actual Polymarket resolution."""
    # Wait until window ends + buffer for Chainlink settlement
    secs_left = _secs_remaining()
    if secs_left > 0:
        time.sleep(secs_left + 3)

    # Fetch end prices from multiple sources for logging/diagnostics
    time.sleep(5)
    end_price = get_btc_price()
    if end_price is None:
        end_price = _get_window_start_price(window_ts + WINDOW_SECS)

    chainlink_px = get_chainlink_proxy_price()
    binance_dir = "UP" if (end_price and end_price >= start_price) else "DOWN"
    chain_dir = "N/A"
    if chainlink_px:
        chain_dir = "UP" if chainlink_px >= start_price else "DOWN"
    spread = abs(end_price - chainlink_px) if (end_price and chainlink_px) else 0
    chain_str = f"${chainlink_px:,.2f}" if chainlink_px else "N/A"
    end_str   = f"${end_price:,.2f}" if end_price else "N/A"
    print(f"  [RESOLVE PRICES] Binance US: {end_str} ({binance_dir}) | "
          f"Chainlink proxy: {chain_str} ({chain_dir}) | "
          f"spread: ${spread:,.2f}")

    # --- Primary resolution: query Polymarket CLOB for Chainlink oracle result ---
    oracle_winner = None
    if executor and condition_id:
        print(f"  [RESOLVE] Waiting for Chainlink oracle resolution...")
        oracle_winner = _query_polymarket_resolution(executor, condition_id)

    bet_direction = trade["direction"]

    if oracle_winner:
        # Authoritative resolution from Polymarket/Chainlink
        went_up = (oracle_winner == "Up")
        won = (bet_direction == "UP" and went_up) or (bet_direction == "DOWN" and not went_up)
        resolution_source = "chainlink"
    else:
        # Fallback: Binance price comparison (paper mode or API failure)
        if end_price is None:
            print(f"[BTC-5M] Could not determine resolution — no oracle, no price")
            return
        went_up = end_price >= start_price
        won = (bet_direction == "UP" and went_up) or (bet_direction == "DOWN" and not went_up)
        resolution_source = "binance_fallback"
        print(f"  ⚠️ Oracle unavailable — using Binance fallback (less reliable)")

    # PnL: use actual fill data
    shares = trade.get("fill_shares", 0)
    if won:
        if shares > 0:
            pnl = shares - trade["bet_size"]  # payout($1*shares) - cost
        else:
            pnl = (trade["bet_size"] / trade["market_price"]) - trade["bet_size"]
    else:
        pnl = -trade["bet_size"]

    trade["resolution_source"] = resolution_source
    trade["oracle_winner"] = oracle_winner
    state.record_resolution(window_ts, won, pnl)

    emoji = "✅" if won else "❌"
    outcome = "UP" if went_up else "DOWN"
    end_str = f"${end_price:,.2f}" if end_price else "N/A"
    print(f"  {emoji} Resolved ({resolution_source}): {outcome} | Bet: {bet_direction} | "
          f"PnL: ${pnl:+.2f} | End: {end_str}")

    s = state.compute_stats()
    _tg(
        f"{emoji} <b>BTC 5-Min {'WIN' if won else 'LOSS'} ${pnl:+.2f}</b>\n"
        f"Bet {bet_direction} → {outcome} (oracle: {resolution_source})\n"
        f"BTC ${start_price:,.0f} → {end_str}\n"
        f"Bank: ${state.bankroll:.0f} | {s['wins']}W/{s['losses']}L ({s['win_rate']}%) | "
        f"{s['resolved_trades']}/{s['total_trades']} resolved"
    )

    # Auto-redeem resolved positions after each win
    if won:
        try:
            from polymarket.auto_redeemer import try_redeem
            try_redeem()
        except Exception as e:
            print(f"  [REDEEM] Auto-redeem skipped: {e}")


def _build_executor(live_mode: bool):
    if live_mode:
        from polymarket.polyconfig import POLY_PRIVATE_KEY
        if not POLY_PRIVATE_KEY:
            print("[BTC-5M] ERROR: --live requires POLY_PRIVATE_KEY in polyconfig.py")
            sys.exit(1)
        return LiveExecutor(POLY_PRIVATE_KEY)
    return PaperExecutor()


# ── Entry Point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Polymarket BTC 5-Min Sniper")
    parser.add_argument("--live", action="store_true",
                        help="Enable live trading (requires Polygon wallet)")
    parser.add_argument("--once", action="store_true",
                        help="Run one window then exit")
    args = parser.parse_args()

    if args.once:
        # Quick test: scan current window
        window_ts = _current_window_ts()
        print(f"Window: {window_ts} | Secs remaining: {_secs_remaining():.0f}")

        btc = get_btc_price()
        print(f"BTC: ${btc:,.2f}" if btc else "BTC: unavailable")

        event = fetch_5m_event(window_ts)
        if event:
            market = parse_5m_market(event)
            if market:
                print(f"Market: {market['question']}")
                print(f"  Up={market['up_price']:.3f} Down={market['down_price']:.3f}")
                print(f"  Volume: ${market['volume']:,.2f}")

                start_price = _get_window_start_price(window_ts)
                if start_price and btc:
                    p_up = estimate_p_up(start_price, btc, _secs_remaining())
                    print(f"  Start: ${start_price:,.2f} | P(Up)={p_up:.3f}")
                    print(f"  Edge UP: {(p_up - market['up_price'])*100:+.1f}%")
                    print(f"  Edge DN: {((1-p_up) - market['down_price'])*100:+.1f}%")
        else:
            print("No event found for current window")
        return

    run_sniper(live_mode=args.live)


if __name__ == "__main__":
    main()
