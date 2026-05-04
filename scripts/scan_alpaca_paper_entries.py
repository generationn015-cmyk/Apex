"""Scan ranked equities with Alpaca paper data for current entry candidates."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.alpaca_paper_runner import decide_signal, fetch_bars, get_clients, load_env


RANKINGS_PATH = ROOT / "runtime" / "strategy_rankings.json"
TOP_SIGNAL_PATH = ROOT / "runtime" / "top_signal_report.json"
OUTPUT_JSON = ROOT / "runtime" / "alpaca_paper_entry_scan.json"
OUTPUT_MD = ROOT / "docs" / "backtests" / "alpaca-paper-entry-scan.md"


def load_ranked_symbols(limit: int) -> list[str]:
    if not RANKINGS_PATH.exists():
        return []
    payload = json.loads(RANKINGS_PATH.read_text(encoding="utf-8"))
    rows = payload.get("ranked") or []
    symbols = [row["symbol"] for row in rows if row.get("pass") and row.get("symbol")]
    return symbols[:limit]


def load_top_signal_map() -> dict[str, dict]:
    if not TOP_SIGNAL_PATH.exists():
        return {}
    payload = json.loads(TOP_SIGNAL_PATH.read_text(encoding="utf-8"))
    return {row["symbol"]: row for row in payload.get("signals") or [] if row.get("symbol")}


def scan_symbols(symbols: list[str]) -> list[dict]:
    env = load_env()
    _trading, data = get_clients(env)
    top_map = load_top_signal_map()
    rows = []
    for symbol in symbols:
        try:
            bars = fetch_bars(data, symbol, limit=100)
            latest = float(bars[-1]["close"]) if bars else 0.0
            decision = decide_signal(bars, has_position=False, entry_price=0, latest_price=latest)
            top = top_map.get(symbol, {})
            row = {
                "symbol": symbol,
                "decision": decision.action,
                "reason": decision.reason,
                "latest_price": round(latest, 2),
                "bars": len(bars),
                "historical_pass": bool(top.get("pass") or top.get("multi_year_pass")),
                "actionable": decision.action == "buy" and bool(top.get("pass") or top.get("multi_year_pass")),
                "score": top.get("score"),
            }
        except Exception as exc:  # noqa: BLE001 - scanner should continue through bad symbols.
            row = {
                "symbol": symbol,
                "decision": "error",
                "reason": str(exc),
                "latest_price": 0.0,
                "bars": 0,
                "historical_pass": False,
                "actionable": False,
                "score": None,
            }
        rows.append(row)
    return sorted(rows, key=lambda row: (row["actionable"], row["score"] or 0), reverse=True)


def write_outputs(rows: list[dict]) -> None:
    generated_at = datetime.now(UTC).isoformat()
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps({"generated_at": generated_at, "signals": rows}, indent=2), encoding="utf-8")

    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Alpaca Paper Entry Scan",
        "",
        f"Generated: {generated_at}",
        "",
        "| Rank | Symbol | Actionable | Decision | Reason | Price | Bars | Score |",
        "|---:|---|---:|---|---|---:|---:|---:|",
    ]
    for index, row in enumerate(rows, 1):
        lines.append(
            "| {rank} | {symbol} | {actionable} | {decision} | {reason} | {price} | {bars} | {score} |".format(
                rank=index,
                symbol=row["symbol"],
                actionable="yes" if row["actionable"] else "no",
                decision=row["decision"],
                reason=row["reason"],
                price=row["latest_price"],
                bars=row["bars"],
                score=row["score"] if row["score"] is not None else "",
            )
        )
    lines.extend(["", "Actionable requires current Alpaca data to say buy and historical gates to pass."])
    OUTPUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default="")
    parser.add_argument("--limit", type=int, default=60)
    args = parser.parse_args()

    symbols = [item.strip().upper() for item in args.symbols.split(",") if item.strip()]
    if not symbols:
        symbols = load_ranked_symbols(args.limit)
    rows = scan_symbols(symbols[: args.limit])
    write_outputs(rows)
    for row in rows:
        print(f"{row['symbol']}: actionable={row['actionable']} decision={row['decision']} reason={row['reason']}")
    print(OUTPUT_MD)


if __name__ == "__main__":
    main()
