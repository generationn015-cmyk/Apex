"""Rank Apex equity candidates using the current paper strategy logic."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_equity_backtest_report import passes_gate, run_symbols
from scripts.equity_universe import default_equity_symbols


def score(row: dict) -> float:
    profit_factor = 999.0 if row.get("profit_factor") == "inf" else float(row.get("profit_factor") or 0)
    return (
        float(row.get("total_return_pct") or 0)
        + profit_factor * 10
        + float(row.get("sharpe") or 0) * 12
        + float(row.get("calmar") or 0) * 8
        - float(row.get("max_drawdown_pct") or 0) * 1.5
        + int(row.get("closed_trades") or 0) * 0.5
    )


def write_outputs(rows: list[dict], json_path: Path, md_path: Path) -> None:
    ranked = sorted(
        [{**row, "pass": passes_gate(row), "score": round(score(row), 2)} for row in rows],
        key=lambda item: item["score"],
        reverse=True,
    )
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps({"generated_at": datetime.now(UTC).isoformat(), "ranked": ranked}, indent=2), encoding="utf-8")
    lines = [
        "# Apex Strategy Ranking",
        "",
        f"Generated: {datetime.now(UTC).isoformat()}",
        "",
        "| Rank | Symbol | Pass | Score | Return % | CAGR % | Sharpe | Calmar | Max DD % | Profit Factor | Closed Trades |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for index, row in enumerate(ranked, 1):
        lines.append(
            f"| {index} | {row['symbol']} | {'yes' if row['pass'] else 'no'} | {row['score']} | {row['total_return_pct']} | {row['cagr_pct']} | {row['sharpe']} | {row['calmar']} | {row['max_drawdown_pct']} | {row['profit_factor']} | {row['closed_trades']} |"
        )
    lines.extend(["", "Paper rule: only candidates passing the gate can be considered for runner changes."])
    md_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--start", default="20160101")
    parser.add_argument("--output-json", default=str(ROOT / "runtime" / "strategy_rankings.json"))
    parser.add_argument("--output-md", default=str(ROOT / "docs" / "backtests" / "strategy-rankings.md"))
    args = parser.parse_args()

    symbols = [symbol.strip().upper() for symbol in args.symbols.split(",") if symbol.strip()]
    if not symbols:
        symbols = default_equity_symbols(args.limit)
    rows = run_symbols(symbols, args.start, datetime.now(UTC).strftime("%Y%m%d"))
    write_outputs(rows, Path(args.output_json), Path(args.output_md))
    print(args.output_md)


if __name__ == "__main__":
    main()
