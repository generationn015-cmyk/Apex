"""Download free official Binance Vision kline data for crypto backtests."""
from __future__ import annotations

import argparse
import csv
import io
import sys
import urllib.request
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def binance_monthly_kline_url(symbol: str, interval: str, month: str, market: str = "spot") -> str:
    symbol = symbol.upper()
    base = _market_path(market)
    return (
        f"https://data.binance.vision/data/{base}/monthly/klines/"
        f"{symbol}/{interval}/{symbol}-{interval}-{month}.zip"
    )


def download_month(symbol: str, interval: str, month: str, market: str, output_dir: Path) -> Path:
    url = binance_monthly_kline_url(symbol, interval, month, market)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{symbol.upper()}-{interval}-{month}.csv"
    if out_path.exists() and out_path.stat().st_size > 0:
        return out_path
    with urllib.request.urlopen(url, timeout=60) as response:
        payload = response.read()
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = [name for name in archive.namelist() if name.endswith(".csv")]
        if not names:
            raise RuntimeError(f"No CSV found inside {url}")
        text = archive.read(names[0]).decode("utf-8")
    rows = list(csv.reader(io.StringIO(text)))
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "open_time",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "close_time",
                "quote_volume",
                "trade_count",
                "taker_buy_base",
                "taker_buy_quote",
                "ignore",
            ]
        )
        writer.writerows(rows)
    return out_path


def _market_path(market: str) -> str:
    aliases = {
        "spot": "spot",
        "um": "futures/um",
        "usdm": "futures/um",
        "usd-m": "futures/um",
        "cm": "futures/cm",
        "coinm": "futures/cm",
        "coin-m": "futures/cm",
    }
    if market not in aliases:
        raise ValueError(f"Unsupported Binance market: {market}")
    return aliases[market]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", default="1h")
    parser.add_argument("--month", required=True, help="YYYY-MM")
    parser.add_argument("--market", default="spot", choices=["spot", "um", "usdm", "usd-m", "cm", "coinm", "coin-m"])
    parser.add_argument("--output-dir", default=str(ROOT / "data" / "history" / "binance"))
    args = parser.parse_args()

    path = download_month(
        symbol=args.symbol,
        interval=args.interval,
        month=args.month,
        market=args.market,
        output_dir=Path(args.output_dir),
    )
    print(path)


if __name__ == "__main__":
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    main()
