"""Generate a local Apex backtest tear sheet from the current paper strategy."""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.backtest_spy_strategy import fetch_free_equity_daily, run_backtest
from scripts.equity_universe import default_equity_symbols
from scripts.run_equity_backtest_report import passes_gate


OUTPUT_DIR = ROOT / "docs" / "backtests" / "tearsheets"
RANKINGS_PATH = ROOT / "runtime" / "strategy_rankings.json"


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


def load_ranked_symbols(limit: int) -> list[str]:
    if RANKINGS_PATH.exists():
        payload = json.loads(RANKINGS_PATH.read_text(encoding="utf-8"))
        ranked = [row.get("symbol") for row in payload.get("ranked", []) if row.get("symbol")]
        if ranked:
            return [str(symbol).upper() for symbol in ranked[:limit]]
    return default_equity_symbols(limit)


def write_index(rows: list[dict], output_dir: Path) -> Path:
    generated_at = datetime.now(UTC).isoformat()
    index_path = output_dir / "index.md"
    lines = [
        "# Apex Backtest Tear Sheets",
        "",
        f"Generated: {generated_at}",
        "",
        "| Symbol | Gate | Return % | Sharpe | Calmar | Max DD % | File |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        filename = f"{row['symbol'].lower()}-tearsheet.md"
        lines.append(
            "| {symbol} | {gate} | {ret} | {sharpe} | {calmar} | {dd} | [{filename}]({filename}) |".format(
                symbol=row["symbol"],
                gate="yes" if passes_gate(row["metrics"]) else "no",
                ret=row["metrics"]["total_return_pct"],
                sharpe=row["metrics"]["sharpe"],
                calmar=row["metrics"]["calmar"],
                dd=row["metrics"]["max_drawdown_pct"],
                filename=filename,
            )
        )
    lines.extend(["", "Research-only tear sheets. They do not approve symbol changes or live trading."])
    index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return index_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--symbols", default="")
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--start", default="20160101")
    parser.add_argument("--end", default=datetime.now(UTC).strftime("%Y%m%d"))
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    if args.symbols:
        symbols = [symbol.strip().upper() for symbol in args.symbols.split(",") if symbol.strip()]
    elif args.limit > 1:
        symbols = load_ranked_symbols(args.limit)
    else:
        symbols = [args.symbol.upper()]

    output_dir = Path(args.output) if args.output and len(symbols) > 1 else OUTPUT_DIR
    rows = []
    for symbol in symbols[: args.limit]:
        source, bars = fetch_free_equity_daily(symbol, args.start, args.end)
        metrics = run_backtest(bars, include_details=True)
        output = Path(args.output) if args.output and len(symbols) == 1 else output_dir / f"{symbol.lower()}-tearsheet.md"
        write_tearsheet(symbol, source, metrics, output)
        rows.append({"symbol": symbol, "source": source, "metrics": metrics, "output": output})
        print(output)
    if len(rows) > 1:
        print(write_index(rows, output_dir))


if __name__ == "__main__":
    main()
