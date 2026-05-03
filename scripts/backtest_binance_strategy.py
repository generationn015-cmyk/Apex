"""Backtest Apex's simple trend/stop strategy on Binance Vision kline CSVs."""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.alpaca_paper_runner import decide_signal
from scripts.download_binance_klines import download_month
from scripts.backtest_spy_strategy import run_backtest


def bars_from_binance_rows(rows: list[dict]) -> list[dict]:
    bars: list[dict] = []
    for row in rows:
        open_time = int(row["open_time"])
        if open_time > 10_000_000_000_000:
            open_time = open_time // 1000
        bars.append(
            {
                "timestamp": datetime.fromtimestamp(open_time / 1000, UTC).isoformat(),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            }
        )
    return bars


def load_binance_csv(path: Path) -> list[dict]:
    with path.open("r", newline="", encoding="utf-8") as f:
        return bars_from_binance_rows(list(csv.DictReader(f)))


def backtest_binance_month(symbol: str, interval: str, month: str, market: str) -> tuple[Path, dict]:
    output_dir = ROOT / "data" / "history" / "binance"
    csv_path = download_month(symbol=symbol, interval=interval, month=month, market=market, output_dir=output_dir)
    bars = load_binance_csv(csv_path)
    metrics = run_backtest(bars, initial_cash=10_000.0, max_notional=5_000.0, periods_per_year=365 * 24)
    return csv_path, metrics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", default="1h")
    parser.add_argument("--month", default="2025-01")
    parser.add_argument("--market", default="spot")
    parser.add_argument("--output", default=str(ROOT / "docs" / "backtests" / "binance-btcusdt-report.md"))
    args = parser.parse_args()

    csv_path, metrics = backtest_binance_month(args.symbol, args.interval, args.month, args.market)
    report = Path(args.output)
    report.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Binance Crypto Backtest Report",
        "",
        f"Generated: {datetime.now(UTC).isoformat()}",
        f"Source CSV: `{csv_path}`",
        f"Symbol: `{args.symbol.upper()}`",
        f"Interval: `{args.interval}`",
        f"Month: `{args.month}`",
        "",
    ]
    lines.extend(f"- {key}: {value}" for key, value in metrics.items())
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for key, value in metrics.items():
        print(f"{key}: {value}")
    print(report)


if __name__ == "__main__":
    main()
