"""Run the Apex equity strategy backtest across symbols and write a gate report."""
from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.backtest_spy_strategy import fetch_free_equity_daily, run_backtest


def passes_gate(metrics: dict) -> bool:
    profit_factor = metrics.get("profit_factor", 0)
    if profit_factor == "inf":
        profit_factor = 999.0
    return (
        float(profit_factor) >= 1.5
        and float(metrics.get("max_drawdown_pct", 999.0)) <= 20.0
        and int(metrics.get("closed_trades", 0)) >= 3
        and float(metrics.get("total_return_pct", -999.0)) > 0
    )


def run_symbols(symbols: list[str], start: str, end: str) -> list[dict]:
    rows: list[dict] = []
    for symbol in symbols:
        source, bars = fetch_free_equity_daily(symbol, start, end)
        metrics = run_backtest(bars)
        rows.append({"symbol": symbol, "source": source, "pass": passes_gate(metrics), **metrics})
    return rows


def write_report(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Equity Backtest Gate Report",
        "",
        f"Generated: {datetime.now(UTC).isoformat()}",
        "",
        "| Symbol | Source | Pass | Return % | Max DD % | Profit Factor | Closed Trades | Win Rate % |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {symbol} | {source} | {passed} | {ret} | {dd} | {pf} | {closed} | {wr} |".format(
                symbol=row["symbol"],
                source=row["source"],
                passed="yes" if row["pass"] else "no",
                ret=row["total_return_pct"],
                dd=row["max_drawdown_pct"],
                pf=row["profit_factor"],
                closed=row["closed_trades"],
                wr=row["win_rate_pct"],
            )
        )
    lines.extend(
        [
            "",
            "Gate: profit factor >= 1.5, max drawdown <= 20%, at least 3 closed trades, positive return.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default="SPY,QQQ,AAPL,MSFT")
    parser.add_argument("--start", default="20160101")
    parser.add_argument("--end", default=datetime.now(UTC).strftime("%Y%m%d"))
    parser.add_argument("--output", default=str(ROOT / "docs" / "backtests" / "equity-gate-report.md"))
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    rows = run_symbols(symbols, args.start, args.end)
    write_report(rows, Path(args.output))
    for row in rows:
        print(f"{row['symbol']}: pass={row['pass']} return={row['total_return_pct']} dd={row['max_drawdown_pct']} pf={row['profit_factor']}")
    print(args.output)


if __name__ == "__main__":
    main()
