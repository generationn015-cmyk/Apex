"""Run rolling walk-forward checks for Apex paper strategy candidates."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.backtest_spy_strategy import fetch_free_equity_daily, run_backtest
from scripts.equity_universe import default_equity_symbols
from scripts.rank_equity_strategies import score
from scripts.run_equity_backtest_report import passes_gate


RANKINGS_PATH = ROOT / "runtime" / "strategy_rankings.json"
OUTPUT_JSON = ROOT / "runtime" / "walk_forward_report.json"
OUTPUT_MD = ROOT / "docs" / "backtests" / "walk-forward-report.md"


def load_symbols(limit: int) -> list[str]:
    if RANKINGS_PATH.exists():
        payload = json.loads(RANKINGS_PATH.read_text(encoding="utf-8"))
        ranked = [row["symbol"] for row in payload.get("ranked", []) if row.get("pass") and row.get("symbol")]
        if ranked:
            return ranked[:limit]
    return default_equity_symbols(limit)


def walk_forward_symbol(
    symbol: str,
    start: str,
    end: str,
    train_bars: int = 756,
    test_bars: int = 252,
) -> dict:
    source, bars = fetch_free_equity_daily(symbol, start, end)
    windows: list[dict] = []
    index = train_bars
    while index + test_bars <= len(bars):
        window = bars[index : index + test_bars]
        metrics = run_backtest(window)
        windows.append(
            {
                "start": window[0].get("timestamp") if window else "",
                "end": window[-1].get("timestamp") if window else "",
                "pass": passes_gate(metrics),
                **metrics,
            }
        )
        index += test_bars
    summary = summarize_windows(windows)
    row = {
        "symbol": symbol,
        "source": source,
        "windows": windows,
        **summary,
    }
    row["score"] = round(score(row), 2)
    row["pass"] = passes_walk_forward(row)
    return row


def summarize_windows(windows: list[dict]) -> dict:
    if not windows:
        return {
            "window_count": 0,
            "pass_rate_pct": 0.0,
            "positive_rate_pct": 0.0,
            "avg_return_pct": 0.0,
            "worst_drawdown_pct": 0.0,
            "avg_sharpe": 0.0,
            "avg_calmar": 0.0,
            "total_return_pct": 0.0,
            "max_drawdown_pct": 999.0,
            "profit_factor": 0.0,
            "closed_trades": 0,
        }
    count = len(windows)
    return {
        "window_count": count,
        "pass_rate_pct": round(sum(1 for item in windows if item.get("pass")) / count * 100, 2),
        "positive_rate_pct": round(sum(1 for item in windows if float(item.get("total_return_pct") or 0) > 0) / count * 100, 2),
        "avg_return_pct": round(sum(float(item.get("total_return_pct") or 0) for item in windows) / count, 2),
        "worst_drawdown_pct": round(max(float(item.get("max_drawdown_pct") or 0) for item in windows), 2),
        "avg_sharpe": round(sum(float(item.get("sharpe") or 0) for item in windows) / count, 2),
        "avg_calmar": round(sum(float(item.get("calmar") or 0) for item in windows) / count, 2),
        "total_return_pct": round(sum(float(item.get("total_return_pct") or 0) for item in windows), 2),
        "max_drawdown_pct": round(max(float(item.get("max_drawdown_pct") or 0) for item in windows), 2),
        "profit_factor": round(sum(_profit_factor_value(item.get("profit_factor")) for item in windows) / count, 2),
        "closed_trades": sum(int(item.get("closed_trades") or 0) for item in windows),
    }


def passes_walk_forward(row: dict) -> bool:
    return (
        int(row.get("window_count") or 0) >= 3
        and float(row.get("positive_rate_pct") or 0) >= 60.0
        and float(row.get("avg_return_pct") or 0) > 0
        and float(row.get("worst_drawdown_pct") or 999) <= 20.0
        and float(row.get("avg_sharpe") or 0) > 0
        and float(row.get("avg_calmar") or 0) > 0
    )


def _profit_factor_value(value: object) -> float:
    if value == "inf":
        return 999.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def write_outputs(rows: list[dict], start: str, end: str) -> None:
    generated_at = datetime.now(UTC).isoformat()
    ranked = sorted(rows, key=lambda row: (row["pass"], row["score"]), reverse=True)
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(
        json.dumps({"generated_at": generated_at, "start": start, "end": end, "walk_forward": ranked}, indent=2),
        encoding="utf-8",
    )
    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Apex Walk-Forward Backtest",
        "",
        f"Generated: {generated_at}",
        f"Window: {start} through {end}",
        "",
        "| Rank | Symbol | Pass | Score | Windows | Positive % | Avg Return % | Worst DD % | Avg Sharpe | Avg Calmar |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for index, row in enumerate(ranked, 1):
        lines.append(
            "| {rank} | {symbol} | {passed} | {score} | {windows} | {positive} | {avg_return} | {dd} | {sharpe} | {calmar} |".format(
                rank=index,
                symbol=row["symbol"],
                passed="yes" if row["pass"] else "no",
                score=row["score"],
                windows=row["window_count"],
                positive=row["positive_rate_pct"],
                avg_return=row["avg_return_pct"],
                dd=row["worst_drawdown_pct"],
                sharpe=row["avg_sharpe"],
                calmar=row["avg_calmar"],
            )
        )
    lines.extend(
        [
            "",
            "Pass requires at least 3 yearly out-of-sample windows, 60% positive windows, positive average return, worst drawdown <= 20%, and positive Sharpe/Calmar.",
        ]
    )
    OUTPUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default="")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--start", default="20160101")
    parser.add_argument("--end", default=datetime.now(UTC).strftime("%Y%m%d"))
    args = parser.parse_args()

    symbols = [symbol.strip().upper() for symbol in args.symbols.split(",") if symbol.strip()] or load_symbols(args.limit)
    rows = [walk_forward_symbol(symbol, args.start, args.end) for symbol in symbols[: args.limit]]
    write_outputs(rows, args.start, args.end)
    for row in rows:
        print(
            f"{row['symbol']}: pass={row['pass']} positive={row['positive_rate_pct']} "
            f"avg_return={row['avg_return_pct']} worst_dd={row['worst_drawdown_pct']}"
        )
    print(OUTPUT_MD)


if __name__ == "__main__":
    main()
