"""
scanner.py — Independent Market Value Scanner (v4 FIXED)
══════════════════════════════════════════════════════════════
Fetches LIVE markets from Gamma API with CLOB fallback,
detects edge via vig-removal + volume momentum.
Uses fixed data_sources.py for Bullpen CLI integration.
══════════════════════════════════════════════════════════════
"""

from __future__ import annotations
import json
import requests
from typing import Optional

from polymarket.polyconfig import GAMMA_API, CLOB_API, MIN_EDGE, KELLY_FRACTION, MAX_POSITION_PCT, STARTING_BANKROLL, MIN_LIQUIDITY, MIN_VOLUME, DATA_DIR


class KellyEngine:
    """Quarter-Kelly sizing with edge threshold."""
    def __init__(self, bankroll=STARTING_BANKROLL, kelly_fraction=KELLY_FRACTION,
                 min_edge=MIN_EDGE, max_position_pct=MAX_POSITION_PCT):
        self.bankroll = bankroll
        self.kelly_fraction = kelly_fraction
        self.min_edge = min_edge
        self.max_position_pct = max_position_pct

    def calculate(self, market_prob: float, market_price: float) -> Optional[dict]:
        edge = market_prob - market_price
        if abs(edge) < self.min_edge:
            return None
        direction = "YES" if edge > 0 else "NO"
        b = (1.0 / market_price) - 1.0 if direction == "YES" else (1.0 / (1.0 - market_price)) - 1.0
        if b <= 0:
            return None
        true_prob = market_prob if direction == "YES" else 1.0 - market_prob
        full_kelly = (true_prob * b - (1.0 - true_prob)) / b
        if full_kelly <= 0:
            return None
        frac = full_kelly * self.kelly_fraction
        bet_size = min(frac * self.bankroll, self.bankroll * self.max_position_pct)
        return {
            "direction": direction,
            "bet_size": round(bet_size, 2),
            "edge": round(abs(edge), 4),
            "kelly_pct": round(full_kelly * 100, 2),
            "market_price": market_price,
            "true_prob": round(true_prob, 4),
        }


def parse_market(m: dict) -> Optional[dict]:
    """Parse a market from Gamma API into a standard format."""
    try:
        # outcomePrices is a JSON string: '["0.525", "0.475"]'
        prices_raw = m.get("outcomePrices", "[]")
        prices = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
        if not prices or len(prices) < 2:
            return None

        yes_price = float(prices[0])
        if yes_price < 0.05 or yes_price > 0.95:
            return None

        liquidity = float(m.get("liquidity", m.get("liquidityNum", 0)) or 0)
        volume = float(m.get("volume", m.get("volumeNum", 0)) or 0)
        volume24h = float(m.get("volume24hr", m.get("volume_24h", 0)) or 0)

        return {
            "question": m.get("question", ""),
            "condition_id": m.get("conditionId", m.get("condition_id", "")),
            "yes_price": yes_price,
            "no_price": 1.0 - yes_price,
            "liquidity": liquidity,
            "volume": volume,
            "volume24h": volume24h,
            "end_date": m.get("endDate", m.get("endDateIso", "")),
            "active": m.get("active", True),
            "closed": m.get("closed", False),
        }
    except Exception:
        return None


def estimate_true_prob(mkt: dict) -> Optional[float]:
    """Estimate true probability via vig-removal + volume momentum."""
    try:
        yes = mkt["yes_price"]
        volume24h = mkt.get("volume24h", 0)
        volume = mkt.get("volume", 0)

        # Vig removal: subtract half-spread estimate
        spread = 0.01 if volume > 100000 else 0.02
        fair_price = yes - spread

        # Volume momentum: high volume = informed money active
        if volume24h > 50000 and volume > 500000:
            momentum = 0.008 if yes > 0.5 else -0.008
            return max(0.10, min(0.90, fair_price + momentum))

        return max(0.10, min(0.90, fair_price))
    except Exception:
        return None


class DeceptionFilter:
    """Filter out thin, low-quality markets."""
    def check(self, liquidity: float, volume: float, yes_price: float = 0.5) -> tuple[bool, str]:
        if liquidity < MIN_LIQUIDITY:
            return False, "LIQUIDITY_TOO_LOW"
        if yes_price < 0.05 or yes_price > 0.95:
            return False, "PRICE_EXTREME"
        if volume < MIN_VOLUME:
            return False, "VOLUME_TOO_LOW"
        return True, "PASS"


_deception_filter = DeceptionFilter()


def scan_markets(kelly: KellyEngine = None, limit: int = 200) -> list[dict]:
    """Scan markets and return signals that pass Kelly + Deception filter."""
    if kelly is None:
        kelly = KellyEngine()

    # Try Gamma API first
    markets_raw = []
    try:
        r = requests.get(
            f"{GAMMA_API}/markets",
            params={"limit": limit, "closed": False, "active": True, "order_by": "volume"},
            timeout=15
        )
        if r.status_code == 200:
            markets_raw = r.json()
    except Exception:
        pass

    # Fallback to CLOB API
    if not markets_raw:
        try:
            r = requests.get(
                f"{CLOB_API}/markets",
                params={"limit": limit, "active": True, "closed": False},
                timeout=15
            )
            if r.status_code == 200:
                data = r.json()
                markets_raw = data.get("data", data) if isinstance(data, dict) else data
        except Exception:
            pass

    signals = []
    for m_raw in markets_raw:
        mkt = parse_market(m_raw)
        if not mkt or not mkt["active"] or mkt["closed"]:
            continue

        passed, reason = _deception_filter.check(mkt["liquidity"], mkt["volume"], mkt["yes_price"])
        if not passed:
            continue

        true_prob = estimate_true_prob(mkt)
        if true_prob is None:
            continue

        result = kelly.calculate(true_prob, mkt["yes_price"])
        if result is None:
            continue

        signals.append({
            "market": mkt["question"][:80],
            "condition_id": mkt["condition_id"],
            "direction": result["direction"],
            "outcome": result["direction"],
            "bet_size": result["bet_size"],
            "edge": result["edge"],
            "confidence": result["true_prob"],
            "liquidity": mkt["liquidity"],
            "volume": mkt["volume"],
        })

    # Sort by edge descending
    signals.sort(key=lambda s: s["edge"], reverse=True)
    return signals


if __name__ == "__main__":
    sigs = scan_markets(limit=100)
    print(f"Found {len(sigs)} value signals")
    for s in sigs[:10]:
        print(f"  {s['market'][:60]:60s} | {s['direction']:3s} | edge={s['edge']:.2%} | ${s['bet_size']:.2f}")
