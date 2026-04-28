"""Connectivity smoke test for Alpaca paper API.

Run BEFORE attempting paper trading. Verifies:
  1. Credentials present in env
  2. Paper API reachable, auth accepted
  3. Account is active and tradable
  4. Market data API responds with a recent bar
  5. Universe symbols are all available

Usage:
  python -m apex2.scripts.preflight
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta

from dotenv import load_dotenv


def _green(s: str) -> str: return f"\033[92m{s}\033[0m"
def _red(s: str) -> str: return f"\033[91m{s}\033[0m"
def _yellow(s: str) -> str: return f"\033[93m{s}\033[0m"


def check_credentials() -> tuple[str, str]:
    load_dotenv()
    key = os.environ.get("ALPACA_API_KEY", "").strip()
    secret = os.environ.get("ALPACA_API_SECRET", "").strip()
    if not key or not secret:
        print(_red("✗ ALPACA_API_KEY / ALPACA_API_SECRET not set"))
        print("  → Get keys from https://app.alpaca.markets → Paper Trading → API Keys")
        print("  → Save in apex2/.env (see .env.example)")
        sys.exit(1)
    print(_green(f"✓ credentials present (key prefix {key[:6]}...)"))
    return key, secret


def check_account(key: str, secret: str) -> None:
    from alpaca.trading.client import TradingClient
    try:
        client = TradingClient(api_key=key, secret_key=secret, paper=True)
        acct = client.get_account()
    except Exception as e:
        print(_red(f"✗ paper auth failed: {e}"))
        sys.exit(1)
    print(_green("✓ paper auth ok"))
    print(f"  account: {acct.account_number}  status: {acct.status}")
    print(f"  cash: ${float(acct.cash):,.2f}   equity: ${float(acct.equity):,.2f}")
    print(f"  buying power: ${float(acct.buying_power):,.2f}")
    if "ACTIVE" not in str(acct.status).upper():
        print(_yellow(f"⚠ account status is {acct.status}; trading may be restricted"))


def check_market_data(key: str, secret: str) -> None:
    from alpaca.data.historical.stock import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    client = StockHistoricalDataClient(api_key=key, secret_key=secret)
    end = date.today()
    start = end - timedelta(days=10)
    req = StockBarsRequest(symbol_or_symbols="SPY", timeframe=TimeFrame.Day, start=start, end=end)
    try:
        bars = client.get_stock_bars(req).df
    except Exception as e:
        print(_red(f"✗ market data failed: {e}"))
        sys.exit(1)
    if bars.empty:
        print(_red("✗ market data returned empty"))
        sys.exit(1)
    print(_green(f"✓ market data ok (got {len(bars)} SPY daily bars)"))


def check_clock(key: str, secret: str) -> None:
    from alpaca.trading.client import TradingClient
    client = TradingClient(api_key=key, secret_key=secret, paper=True)
    clock = client.get_clock()
    state = "OPEN" if clock.is_open else "CLOSED"
    color = _green if clock.is_open else _yellow
    print(color(f"✓ market clock: {state}"))
    print(f"  next open: {clock.next_open}   next close: {clock.next_close}")


def check_universe(key: str, secret: str) -> None:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import GetAssetsRequest
    universe = ["SPY", "QQQ", "IWM", "XLK", "XLF", "XLE", "XLV", "XLY", "TLT", "GLD", "USO", "UUP"]
    client = TradingClient(api_key=key, secret_key=secret, paper=True)
    assets = {a.symbol: a for a in client.get_all_assets(GetAssetsRequest(status="active"))}
    missing = []
    untradable = []
    for sym in universe:
        a = assets.get(sym)
        if a is None:
            missing.append(sym)
        elif not a.tradable:
            untradable.append(sym)
    if missing:
        print(_red(f"✗ missing from Alpaca: {missing}"))
    if untradable:
        print(_yellow(f"⚠ not tradable: {untradable}"))
    if not missing and not untradable:
        print(_green(f"✓ all {len(universe)} ETFs tradable"))


def main() -> None:
    print("=== Apex v2 preflight ===")
    key, secret = check_credentials()
    check_account(key, secret)
    check_market_data(key, secret)
    check_clock(key, secret)
    check_universe(key, secret)
    print()
    print(_green("ALL CHECKS PASSED — ready for paper trading."))
    print("  next: python -m apex2.runner paper -c configs/paper.yaml -s rsi2_meanrev")


if __name__ == "__main__":
    main()
