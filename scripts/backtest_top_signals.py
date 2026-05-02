"""Backtest top ranked symbols and mark currently actionable paper signals."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.alpaca_paper_runner import decide_signal
from scripts.backtest_spy_strategy import fetch_free_equity_daily, run_backtest
from scripts.rank_equity_strategies import score
from scripts.run_equity_backtest_report import passes_gate


RANKINGS_PATH = ROOT / "runtime" / "strategy_rankings.json"
OUTPUT_JSON = ROOT / "runtime" / "top_signal_report.json"
OUTPUT_MD = ROOT / "docs" / "backtests" / "top-signal-report.md"


def load_ranked_symbols(limit: int) -> list[str]:
    if not RANKINGS_PATH.exists():
        return ["NVDA", "META", "GOOGL", "AAPL", "MSFT"][:limit]
    payload = json.loads(RANKINGS_PATH.read_text(encoding="utf-8"))
    rows = payload.get("ranked") or []
    symbols = [row["symbol"] for row in rows if row.get("pass") and row.get("symbol")]
    return symbols[:limit]


def analyze_symbol(symbol: str, start: str, end: str) -> dict:
    source, bars = fetch_free_equity_daily(symbol, start, end)
    full = run_backtest(bars)
    recent_3y = run_backtest(bars[-756:]) if len(bars) >= 80 else run_backtest(bars)
    recent_1y = run_backtest(bars[-252:]) if len(bars) >= 80 else run_backtest(bars)
    latest_price = float(bars[-1]["close"]) if bars else 0.0
    current = decide_signal(
        bars,
        has_position=bool(full.get("open_qty")),
        entry_price=latest_price,
        latest_price=latest_price,
    )
    gate_pass = passes_gate(full) and passes_gate(recent_3y)
    actionable = gate_pass and current.action == "buy" and latest_price > 0
    row = {
        "symbol": symbol,
        "source": source,
        "decision": current.action,
        "reason": current.reason,
        "latest_price": round(latest_price, 2),
        "pass": gate_pass,
        "actionable": actionable,
        "full": full,
        "recent_3y": recent_3y,
        "recent_1y": recent_1y,
    }
    row["score"] = round(score({"closed_trades": full["closed_trades"], **full}), 2)
    return row


def write_outputs(rows: list[dict]) -> None:
    generated_at = datetime.now(UTC).isoformat()
    ranked = sorted(rows, key=lambda row: (row["actionable"], row["pass"], row["score"]), reverse=True)
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps({"generated_at": generated_at, "signals": ranked}, indent=2), encoding="utf-8")
    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Apex Top Signal Backtest",
        "",
        f"Generated: {generated_at}",
        "",
        "| Rank | Symbol | Actionable | Decision | Score | Full Return % | 3Y Return % | 3Y DD % | 1Y Return % |",
        "|---:|---|---:|---|---:|---:|---:|---:|---:|",
    ]
    for index, row in enumerate(ranked, 1):
        lines.append(
            "| {rank} | {symbol} | {actionable} | {decision}/{reason} | {score} | {full_ret} | {recent_ret} | {recent_dd} | {one_year_ret} |".format(
                rank=index,
                symbol=row["symbol"],
                actionable="yes" if row["actionable"] else "no",
                decision=row["decision"],
                reason=row["reason"],
                score=row["score"],
                full_ret=row["full"]["total_return_pct"],
                recent_ret=row["recent_3y"]["total_return_pct"],
                recent_dd=row["recent_3y"]["max_drawdown_pct"],
                one_year_ret=row["recent_1y"]["total_return_pct"],
            )
        )
    lines.extend(
        [
            "",
            "Actionable means the symbol passes full and 3Y gates and the current paper logic says buy.",
            "This is a paper-trading research signal, not live-trading approval.",
        ]
    )
    OUTPUT_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default="")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--start", default="20160101")
    parser.add_argument("--end", default=datetime.now(UTC).strftime("%Y%m%d"))
    args = parser.parse_args()

    symbols = [item.strip().upper() for item in args.symbols.split(",") if item.strip()]
    if not symbols:
        symbols = load_ranked_symbols(args.limit)
    rows = [analyze_symbol(symbol, args.start, args.end) for symbol in symbols[: args.limit]]
    write_outputs(rows)
    for row in rows:
        print(f"{row['symbol']}: actionable={row['actionable']} decision={row['decision']} score={row['score']}")
    print(OUTPUT_MD)


if __name__ == "__main__":
    main()
