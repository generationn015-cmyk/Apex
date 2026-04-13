"""
One-shot reconciliation for orphaned BTC 5-min sniper trades.

Finds trades in btc_5m_state.json with resolved=false whose window has
already closed, fetches the actual BTC outcome from Binance US klines,
and updates each trade's won/pnl/bankroll in place.

Safe to re-run: trades marked reconciled=true are skipped.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

STATE_FILE = Path(__file__).parent / "data" / "btc_5m_state.json"
BINANCE_KLINE_URL = "https://api.binance.us/api/v3/klines"
HDR = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
WINDOW_SECS = 300


def fetch_window_outcome(window_ts: int) -> tuple[float, float] | None:
    """Return (start_price, end_price) for a closed 5-min BTC window."""
    params = {
        "symbol": "BTCUSDT",
        "interval": "1m",
        "startTime": window_ts * 1000,
        "endTime": (window_ts + WINDOW_SECS) * 1000,
        "limit": 6,
    }
    try:
        r = requests.get(BINANCE_KLINE_URL, params=params, headers=HDR, timeout=10)
        if r.status_code != 200:
            return None
        klines = r.json()
        if not klines:
            return None
        start_price = float(klines[0][1])   # open of first candle
        end_price = float(klines[-1][4])    # close of last candle
        return start_price, end_price
    except Exception as e:
        print(f"  fetch error: {e}")
        return None


def main():
    if not STATE_FILE.exists():
        print(f"state file not found: {STATE_FILE}")
        return

    state = json.loads(STATE_FILE.read_text())
    trades = state.get("trades", [])
    now = time.time()

    orphans = [t for t in trades if not t.get("resolved")]
    print(f"Found {len(orphans)} unresolved trades out of {len(trades)} total")

    reconciled_count = 0
    bankroll_delta = 0.0

    for t in orphans:
        if t.get("reconciled"):
            print(f"  skip already-reconciled window_ts={t.get('window_ts')}")
            continue

        window_ts = t.get("window_ts")
        if not window_ts:
            print(f"  skip trade with no window_ts: {t.get('order_id')}")
            continue

        window_end = window_ts + WINDOW_SECS
        if window_end > now - 60:
            print(f"  skip live window window_ts={window_ts} (ends in {window_end - now:.0f}s)")
            continue

        outcome = fetch_window_outcome(window_ts)
        if not outcome:
            print(f"  skip window_ts={window_ts}: could not fetch klines")
            continue

        start_price, end_price = outcome
        actual_dir = "UP" if end_price > start_price else "DOWN"
        bet_dir = t.get("direction")
        won = (actual_dir == bet_dir)

        bet_size = float(t.get("bet_size", 0))
        market_price = float(t.get("market_price", 0.5)) or 0.5
        if won:
            pnl = bet_size * (1.0 - market_price) / market_price
        else:
            pnl = -bet_size

        t["resolved"] = True
        t["won"] = won
        t["pnl"] = round(pnl, 2)
        t["start_price"] = start_price
        t["end_price"] = end_price
        t["actual_direction"] = actual_dir
        t["reconciled"] = True

        stake_return = bet_size + pnl
        bankroll_delta += stake_return

        print(
            f"  RECONCILED window_ts={window_ts} "
            f"{bet_dir} vs actual {actual_dir} "
            f"{'WIN' if won else 'LOSS'} pnl={pnl:+.2f} "
            f"start={start_price:.2f} end={end_price:.2f}"
        )
        reconciled_count += 1
        time.sleep(0.3)  # be nice to binance

    if reconciled_count == 0:
        print("nothing to reconcile")
        return

    old_bankroll = float(state.get("bankroll", 0))
    state["bankroll"] = round(old_bankroll + bankroll_delta, 2)
    state["updated"] = datetime.now(timezone.utc).isoformat()

    # Recompute stats block
    resolved = [t for t in trades if t.get("resolved")]
    wins = sum(1 for t in resolved if t.get("won"))
    losses = len(resolved) - wins
    pnl_total = round(sum(t.get("pnl", 0) for t in resolved), 2)
    state["stats"] = {
        "total_trades": len(trades),
        "resolved_trades": len(resolved),
        "pending_trades": len(trades) - len(resolved),
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / len(resolved) * 100, 1) if resolved else 0.0,
        "realized_pnl": pnl_total,
    }

    STATE_FILE.write_text(json.dumps(state, indent=2))
    print(
        f"\nReconciled {reconciled_count} trades. "
        f"Bankroll: ${old_bankroll:.2f} -> ${state['bankroll']:.2f} "
        f"(delta {bankroll_delta:+.2f}). "
        f"New stats: {state['stats']}"
    )


if __name__ == "__main__":
    main()
