"""Generate an after-close missed-opportunity report from the paper journal.

This joins cap-driven `risk_block:*` rows with the latest historical gates so we can
separate "good blocks" (gate fails) from "bad blocks" (gate passes but we were capped).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

JOURNAL_PATH = ROOT / "data" / "paper_journal.csv"
OUTPUT_PATH = ROOT / "runtime" / "evolution" / "missed_opportunity_report.md"

ACTIVE_CANDIDATES_PATH = ROOT / "runtime" / "active_paper_candidates.json"
STRATEGY_RANKINGS_JSON_PATH = ROOT / "runtime" / "strategy_rankings.json"
STRATEGY_RANKINGS_MD_PATH = ROOT / "docs" / "backtests" / "strategy-rankings.md"


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_pass_symbols() -> set[str]:
    # 1) Explicit actionable allowlist
    if ACTIVE_CANDIDATES_PATH.exists():
        payload = _read_json(ACTIVE_CANDIDATES_PATH)
        rows = payload.get("active") or []
        symbols = {str(row.get("symbol", "")).upper() for row in rows if row.get("symbol")}
        if symbols:
            return symbols

    # 2) Rankings JSON
    if STRATEGY_RANKINGS_JSON_PATH.exists():
        payload = _read_json(STRATEGY_RANKINGS_JSON_PATH)
        rows = payload.get("ranked") or []
        symbols = {str(row.get("symbol", "")).upper() for row in rows if row.get("symbol") and bool(row.get("pass"))}
        if symbols:
            return symbols

    # 3) Rankings markdown fallback
    if not STRATEGY_RANKINGS_MD_PATH.exists():
        return set()
    symbols: set[str] = set()
    for line in STRATEGY_RANKINGS_MD_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or stripped.count("|") < 4:
            continue
        parts = [part.strip() for part in stripped.strip("|").split("|")]
        if len(parts) < 3 or parts[0].lower() == "rank":
            continue
        symbol = parts[1].upper()
        passed = parts[2].lower()
        if symbol and passed in {"yes", "true", "1"}:
            symbols.add(symbol)
    return symbols


def iter_risk_blocks(date_prefix: str | None = None) -> list[dict]:
    if not JOURNAL_PATH.exists():
        return []
    with JOURNAL_PATH.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = []
        for row in reader:
            reason = str(row.get("reason") or "")
            if not reason.startswith("risk_block:"):
                continue
            if date_prefix and not str(row.get("timestamp") or "").startswith(date_prefix):
                continue
            symbol = str(row.get("symbol") or "").upper()
            rows.append({"timestamp": row.get("timestamp"), "symbol": symbol, "reason": reason})
        return rows


def write_report(rows: list[dict], pass_symbols: set[str], date_prefix: str | None = None) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(UTC).isoformat()

    by_symbol = Counter(row["symbol"] for row in rows if row.get("symbol"))
    by_reason = Counter(row["reason"] for row in rows if row.get("reason"))

    bad_blocks = [row for row in rows if row.get("symbol") in pass_symbols]
    good_blocks = [row for row in rows if row.get("symbol") and row.get("symbol") not in pass_symbols]

    lines = [
        "# Missed Opportunity Report (Paper)",
        "",
        f"Generated: {generated_at}",
        f"Window: {date_prefix or 'all'}",
        "",
        "Definitions:",
        "- bad block: symbol passes historical gate (should have been actionable), but was blocked by caps.",
        "- good block: symbol fails historical gate (block is desirable), regardless of cap pressure.",
        "",
        f"Total risk blocks: {len(rows)}",
        f"Bad blocks (gate pass): {len(bad_blocks)}",
        f"Good blocks (gate fail): {len(good_blocks)}",
        "",
        "## Top blocked symbols",
        "",
        "| Rank | Symbol | Blocks | Gate |",
        "|---:|---|---:|---|",
    ]
    for index, (symbol, count) in enumerate(by_symbol.most_common(20), 1):
        gate = "pass" if symbol in pass_symbols else "fail/unknown"
        lines.append(f"| {index} | {symbol} | {count} | {gate} |")

    lines.extend(
        [
            "",
            "## Block reasons",
            "",
            "| Count | Reason |",
            "|---:|---|",
        ]
    )
    for reason, count in by_reason.most_common(20):
        lines.append(f"| {count} | {reason} |")

    OUTPUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--date",
        default="",
        help="Optional UTC date prefix filter (YYYY-MM-DD), e.g. 2026-05-05.",
    )
    args = parser.parse_args()

    date_prefix = args.date.strip() or None
    pass_symbols = load_pass_symbols()
    rows = iter_risk_blocks(date_prefix=date_prefix)
    write_report(rows, pass_symbols, date_prefix=date_prefix)
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()
