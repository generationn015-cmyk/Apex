"""Generate a local Apex backtest tear sheet from the current paper strategy."""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.backtest_spy_strategy import fetch_free_equity_daily, run_backtest
from scripts.run_equity_backtest_report import passes_gate


OUTPUT_DIR = ROOT / "docs" / "backtests" / "tearsheets"


def monthly_returns(equity_curve: list[dict]) -> list[dict]:
    by_month: dict[str, list[float]] = defaultdict(list)
    for point in equity_curve:
        timestamp = str(point.get("timestamp") or "")
        if len(timestamp) < 7:
            continue
        by_month[timestamp[:7]].append(float(point.get("equity") or 0))
    rows = []
    for month, values in sorted(by_month.items()):
        if len(values) < 2 or values[0] <= 0:
            continue
        rows.append({"month": month, "return_pct": round((values[-1] / values[0] - 1) * 100, 2)})
    return rows


def drawdown_table(equity_curve: list[dict], limit: int = 10) -> list[dict]:
    peak = 0.0
    rows = []
    for point in equity_curve:
        equity = float(point.get("equity") or 0)
        peak = max(peak, equity)
        drawdown = (peak - equity) / peak * 100 if peak else 0.0
        rows.append({"date": point.get("timestamp") or "", "drawdown_pct": round(drawdown, 2), "equity": round(equity, 2)})
    return sorted(rows, key=lambda row: row["drawdown_pct"], reverse=True)[:limit]


def write_tearsheet(symbol: str, source: str, metrics: dict, output: Path) -> None:
    monthly = monthly_returns(metrics.get("equity_curve") or [])
    drawdowns = drawdown_table(metrics.get("equity_curve") or [])
    closed_pnls = metrics.get("closed_trade_pnls") or []
    avg_trade = round(sum(closed_pnls) / len(closed_pnls), 2) if closed_pnls else 0.0
    best_trade = max(closed_pnls) if closed_pnls else 0.0
    worst_trade = min(closed_pnls) if closed_pnls else 0.0
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Apex Backtest Tear Sheet - {symbol}",
        "",
        f"Generated: {datetime.now(UTC).isoformat()}",
        f"Source: {source}",
        "Mode: research-only; no orders placed.",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Pass Gate | {'yes' if passes_gate(metrics) else 'no'} |",
        f"| Bars | {metrics['bars']} |",
        f"| Window | {metrics['first_date']} to {metrics['last_date']} |",
        f"| Final Equity | ${metrics['final_equity']} |",
        f"| Total Return % | {metrics['total_return_pct']} |",
        f"| CAGR % | {metrics['cagr_pct']} |",
        f"| Sharpe | {metrics['sharpe']} |",
        f"| Sortino | {metrics['sortino']} |",
        f"| Calmar | {metrics['calmar']} |",
        f"| Max Drawdown % | {metrics['max_drawdown_pct']} |",
        f"| Exposure % | {metrics['exposure_pct']} |",
        f"| Profit Factor | {metrics['profit_factor']} |",
        f"| Closed Trades | {metrics['closed_trades']} |",
        f"| Win Rate % | {metrics['win_rate_pct']} |",
        f"| Avg Closed Trade | ${avg_trade} |",
        f"| Best Closed Trade | ${best_trade} |",
        f"| Worst Closed Trade | ${worst_trade} |",
        "",
        "## Worst Drawdowns",
        "",
        "| Rank | Date | Drawdown % | Equity |",
        "|---:|---|---:|---:|",
    ]
    for index, row in enumerate(drawdowns, 1):
        lines.append(f"| {index} | {row['date']} | {row['drawdown_pct']} | ${row['equity']} |")
    lines.extend(
        [
            "",
            "## Monthly Returns",
            "",
            "| Month | Return % |",
            "|---|---:|",
        ]
    )
    for row in monthly[-36:]:
        lines.append(f"| {row['month']} | {row['return_pct']} |")
    lines.extend(
        [
            "",
            "## Caveats",
            "",
            "- This report uses free research data, not a live-trading approval source.",
            "- Current gate remains paper-first and requires separate approval before any execution change.",
            "- Results do not include commissions, borrow costs, or all possible real-world slippage.",
        ]
    )
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--start", default="20160101")
    parser.add_argument("--end", default=datetime.now(UTC).strftime("%Y%m%d"))
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    symbol = args.symbol.upper()
    source, bars = fetch_free_equity_daily(symbol, args.start, args.end)
    metrics = run_backtest(bars, include_details=True)
    output = Path(args.output) if args.output else OUTPUT_DIR / f"{symbol.lower()}-tearsheet.md"
    write_tearsheet(symbol, source, metrics, output)
    print(output)


if __name__ == "__main__":
    main()
