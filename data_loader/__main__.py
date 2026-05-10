"""
CLI: python -m data_loader [options]

Downloads historical OHLCV + funding-rate data from Binance's public archive
into data/historical/. Idempotent — safe to re-run; it picks up where it left off.

Examples:
    python -m data_loader                                    # defaults: BTC/ETH/SOL, 5m/15m/1h, 2 years
    python -m data_loader --pairs BTCUSDT,ETHUSDT --years 1
    python -m data_loader --no-funding                       # candles only
"""
from __future__ import annotations

import argparse
import logging
import sys

from data_loader.binance_downloader import download_funding, download_klines


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="data_loader")
    p.add_argument(
        "--pairs", default="BTCUSDT,ETHUSDT,SOLUSDT",
        help="Comma-separated USDT-perp pairs (default: BTCUSDT,ETHUSDT,SOLUSDT)",
    )
    p.add_argument(
        "--timeframes", default="5m,15m,1h",
        help="Comma-separated kline intervals (default: 5m,15m,1h)",
    )
    p.add_argument(
        "--years", type=float, default=2.0,
        help="How many years of history to fetch (default: 2.0)",
    )
    p.add_argument("--no-funding", action="store_true", help="Skip funding rates")
    p.add_argument("--verbose", "-v", action="store_true")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )

    pairs = [p.strip() for p in args.pairs.split(",") if p.strip()]
    tfs = [t.strip() for t in args.timeframes.split(",") if t.strip()]

    print(f"\n=== APEX historical data loader ===")
    print(f"  pairs:     {pairs}")
    print(f"  timeframes:{tfs}")
    print(f"  years:     {args.years}")
    print(f"  funding:   {'no' if args.no_funding else 'yes'}\n")

    for pair in pairs:
        for tf in tfs:
            try:
                download_klines(pair, tf, years=args.years)
            except Exception as e:
                logging.exception("klines %s %s failed: %s", pair, tf, e)
        if not args.no_funding:
            try:
                download_funding(pair, years=args.years)
            except Exception as e:
                logging.exception("funding %s failed: %s", pair, e)

    print("\nDone. Files under data/historical/<pair>/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
