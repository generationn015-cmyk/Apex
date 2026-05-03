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
from scripts.equity_universe import default_equity_symbols
from scripts.rank_equity_strategies import score
from scripts.run_equity_backtest_report import passes_gate


RANKINGS_PATH = ROOT / "runtime" / "strategy_rankings.json"
OUTPUT_JSON = ROOT / "runtime" / "top_signal_report.json"
OUTPUT_MD = ROOT / "docs" / "backtests" / "top-signal-report.md"
ACTIVE_CANDIDATES_PATH = ROOT / "runtime" / "active_paper_candidates.json"

WINDOWS = {
    "full": None,
    "recent_5y": 1260,
    "recent_3y": 756,
    "recent_1y": 252,
    "recent_6m": 126,
}


def load_ranked_symbols(limit: int) -> list[str]:
    if not RANKINGS_PATH.exists():
        return default_equity_symbols(limit)
    payload = json.loads(RANKINGS_PATH.read_text(encoding="utf-8"))
    rows = payload.get("ranked") or []
    symbols = [row["symbol"] for row in rows if row.get("pass") and row.get("symbol")]
    if symbols:
        return symbols[:limit]
    return [row["symbol"] for row in rows if row.get("symbol")][:limit] or default_equity_symbols(limit)


def run_window_backtests(bars: list[dict]) -> dict[str, dict]:
    windows = {}
    for name, lookback in WINDOWS.items():
        window_bars = bars if lookback is None or len(bars) < lookback else bars[-lookback:]
        windows[name] = run_backtest(window_bars)
    return windows


def passes_multi_year_gate(windows: dict[str, dict]) -> bool:
    required = ("full", "recent_5y", "recent_3y")
    return all(passes_gate(windows[name]) for name in required)


def analyze_symbol(symbol: str, start: str, end: str) -> dict:
    source, bars = fetch_free_equity_daily(symbol, start, end)
    windows = run_window_backtests(bars)
    full = windows["full"]
    latest_price = float(bars[-1]["close"]) if bars else 0.0
    current = decide_signal(
        bars,
        has_position=bool(full.get("open_qty")),
        entry_price=latest_price,
        latest_price=latest_price,
    )
    gate_pass = passes_multi_year_gate(windows)
    actionable = gate_pass and current.action == "buy" and latest_price > 0
    row = {
        "symbol": symbol,
        "source": source,
        "decision": current.action,
        "reason": current.reason,
        "latest_price": round(latest_price, 2),
        "pass": gate_pass,
        "multi_year_pass": gate_pass,
        "actionable": actionable,
        **windows,
    }
    row["score"] = round(score({"closed_trades": full["closed_trades"], **full}), 2)
    return row


def write_active_candidates(rows: list[dict]) -> None:
    generated_at = datetime.now(UTC).isoformat()
    active = [
        {
            "symbol": row["symbol"],
            "decision": row["decision"],
            "reason": row["reason"],
            "score": row["score"],
            "latest_price": row["latest_price"],
            "status": "paper-candidate",
            "basis": "full-history-plus-5y-and-3y-backtest-gates",
        }
        for row in rows
        if row.get("actionable")
    ]
    ACTIVE_CANDIDATES_PATH.parent.mkdir(parents=True, exist_ok=True)
    ACTIVE_CANDIDATES_PATH.write_text(
        json.dumps({"generated_at": generated_at, "active": active}, indent=2),
        encoding="utf-8",
    )


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
        "| Rank | Symbol | Actionable | Decision | Score | Full Return % | Full Sharpe | 5Y Return % | 5Y Calmar | 5Y DD % | 3Y Return % | 3Y DD % | 1Y Return % |",
        "|---:|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for index, row in enumerate(ranked, 1):
        lines.append(
            "| {rank} | {symbol} | {actionable} | {decision}/{reason} | {score} | {full_ret} | {full_sharpe} | {five_year_ret} | {five_year_calmar} | {five_year_dd} | {three_year_ret} | {three_year_dd} | {one_year_ret} |".format(
                rank=index,
                symbol=row["symbol"],
                actionable="yes" if row["actionable"] else "no",
                decision=row["decision"],
                reason=row["reason"],
                score=row["score"],
                full_ret=row["full"]["total_return_pct"],
                full_sharpe=row["full"]["sharpe"],
                five_year_ret=row["recent_5y"]["total_return_pct"],
                five_year_calmar=row["recent_5y"]["calmar"],
                five_year_dd=row["recent_5y"]["max_drawdown_pct"],
                three_year_ret=row["recent_3y"]["total_return_pct"],
                three_year_dd=row["recent_3y"]["max_drawdown_pct"],
                one_year_ret=row["recent_1y"]["total_return_pct"],
            )
        )
    lines.extend(
        [
            "",
            "Actionable means the symbol passes full, 5Y, and 3Y gates and the current paper logic says buy.",
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
    parser.add_argument("--activate-top", action="store_true")
    args = parser.parse_args()

    symbols = [item.strip().upper() for item in args.symbols.split(",") if item.strip()]
    if not symbols:
        symbols = load_ranked_symbols(args.limit)
    rows = [analyze_symbol(symbol, args.start, args.end) for symbol in symbols[: args.limit]]
    write_outputs(rows)
    if args.activate_top:
        write_active_candidates(rows)
    for row in rows:
        print(f"{row['symbol']}: actionable={row['actionable']} decision={row['decision']} score={row['score']}")
    print(OUTPUT_MD)
    if args.activate_top:
        print(ACTIVE_CANDIDATES_PATH)


if __name__ == "__main__":
    main()
