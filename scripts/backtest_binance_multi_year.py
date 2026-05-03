"""Run multi-month Binance Vision crypto backtests for Apex research."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.backtest_binance_strategy import load_binance_csv
from scripts.backtest_spy_strategy import run_backtest
from scripts.crypto_universe import default_crypto_symbols
from scripts.download_binance_klines import download_month
from scripts.rank_equity_strategies import score
from scripts.run_equity_backtest_report import passes_gate


OUTPUT_JSON = ROOT / "runtime" / "crypto_signal_report.json"
OUTPUT_MD = ROOT / "docs" / "backtests" / "crypto-signal-report.md"


def month_range(start_month: str, end_month: str) -> list[str]:
    start_year, start_mon = [int(part) for part in start_month.split("-")]
    end_year, end_mon = [int(part) for part in end_month.split("-")]
    months: list[str] = []
    year, month = start_year, start_mon
    while (year, month) <= (end_year, end_mon):
        months.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year += 1
            month = 1
    return months


def latest_complete_month(today: datetime | None = None) -> str:
    current = today or datetime.now(UTC)
    year = current.year
    month = current.month - 1
    if month == 0:
        year -= 1
        month = 12
    return f"{year:04d}-{month:02d}"


def analyze_symbol(symbol: str, interval: str, months: list[str], market: str) -> dict:
    output_dir = ROOT / "data" / "history" / "binance"
    bars: list[dict] = []
    loaded_months: list[str] = []
    failed_months: list[str] = []
    for month in months:
        try:
            csv_path = download_month(symbol=symbol, interval=interval, month=month, market=market, output_dir=output_dir)
            bars.extend(load_binance_csv(csv_path))
            loaded_months.append(month)
        except Exception:
            failed_months.append(month)
    bars = sorted(bars, key=lambda bar: bar.get("timestamp", ""))
    metrics = run_backtest(bars, initial_cash=10_000.0, max_notional=5_000.0, periods_per_year=365 * 24)
    row = {
        "symbol": symbol,
        "source": "binance-vision",
        "market": market,
        "interval": interval,
        "months_requested": len(months),
        "months_loaded": len(loaded_months),
        "failed_months": failed_months,
        "pass": passes_gate(metrics),
        **metrics,
    }
    row["score"] = round(score(row), 2)
    return row


def write_outputs(rows: list[dict], start_month: str, end_month: str) -> None:
    generated_at = datetime.now(UTC).isoformat()
    ranked = sorted(rows, key=lambda row: (row["pass"], row["score"]), reverse=True)
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(
        json.dumps(
            {
                "generated_at": generated_at,
                "start_month": start_month,
                "end_month": end_month,
                "signals": ranked,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Apex Crypto Signal Backtest",
        "",
        f"Generated: {generated_at}",
        f"Window: {start_month} through {end_month}",
        "Source: Binance Vision public monthly klines",
        "",
        "| Rank | Symbol | Pass | Score | Return % | CAGR % | Sharpe | Calmar | Max DD % | Profit Factor | Closed Trades | Months Loaded |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for index, row in enumerate(ranked, 1):
        lines.append(
            "| {rank} | {symbol} | {passed} | {score} | {ret} | {cagr} | {sharpe} | {calmar} | {dd} | {pf} | {closed} | {months} |".format(
                rank=index,
                symbol=row["symbol"],
                passed="yes" if row["pass"] else "no",
                score=row["score"],
                ret=row["total_return_pct"],
                cagr=row["cagr_pct"],
                sharpe=row["sharpe"],
                calmar=row["calmar"],
                dd=row["max_drawdown_pct"],
                pf=row["profit_factor"],
                closed=row["closed_trades"],
                months=row["months_loaded"],
            )
        )
    lines.extend(
        [
            "",
            "Crypto results are research-only. They do not change the Alpaca paper runner.",
        ]
    )
    OUTPUT_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default="")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--interval", default="1h")
    parser.add_argument("--start-month", default="2023-01")
    parser.add_argument("--end-month", default=latest_complete_month())
    parser.add_argument("--market", default="spot")
    args = parser.parse_args()

    symbols = [symbol.strip().upper() for symbol in args.symbols.split(",") if symbol.strip()]
    if not symbols:
        symbols = default_crypto_symbols(args.limit)
    months = month_range(args.start_month, args.end_month)
    rows = [analyze_symbol(symbol, args.interval, months, args.market) for symbol in symbols[: args.limit]]
    write_outputs(rows, args.start_month, args.end_month)
    for row in rows:
        print(
            f"{row['symbol']}: pass={row['pass']} score={row['score']} "
            f"return={row['total_return_pct']} dd={row['max_drawdown_pct']} months={row['months_loaded']}"
        )
    print(OUTPUT_MD)


if __name__ == "__main__":
    main()
