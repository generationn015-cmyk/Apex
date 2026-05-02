"""
Backtest the current Apex Alpaca paper strategy on daily bars.

Default source tries Stooq first, then Yahoo chart data if Stooq requires
an API key/captcha. Both are free sources suitable for research prototypes.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import sys
import urllib.request
from datetime import UTC, datetime, time as dt_time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.alpaca_paper_runner import decide_signal


def fetch_stooq_daily(symbol: str, start: str, end: str) -> list[dict]:
    stooq_symbol = symbol.lower()
    if "." not in stooq_symbol:
        stooq_symbol = f"{stooq_symbol}.us"
    url = f"https://stooq.com/q/d/l/?s={stooq_symbol}&d1={start}&d2={end}&i=d"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        text = response.read().decode("utf-8")
    if "Get your apikey" in text:
        return []
    rows = csv.DictReader(io.StringIO(text))
    bars: list[dict] = []
    for row in rows:
        if not row.get("Close") or row["Close"] == "No data":
            continue
        bars.append(
            {
                "timestamp": row["Date"],
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": float(row["Volume"]),
            }
        )
    return bars


def fetch_yahoo_chart_daily(symbol: str, start: str, end: str) -> list[dict]:
    start_dt = datetime.strptime(start, "%Y%m%d").replace(tzinfo=UTC)
    end_dt = datetime.strptime(end, "%Y%m%d").replace(tzinfo=UTC)
    period1 = int(datetime.combine(start_dt.date(), dt_time.min, tzinfo=UTC).timestamp())
    period2 = int(datetime.combine(end_dt.date(), dt_time.max, tzinfo=UTC).timestamp())
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?period1={period1}&period2={period2}&interval=1d&events=history"
    )
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    result = payload["chart"]["result"][0]
    timestamps = result["timestamp"]
    quote = result["indicators"]["quote"][0]
    bars: list[dict] = []
    for idx, ts in enumerate(timestamps):
        close = quote["close"][idx]
        if close is None:
            continue
        bars.append(
            {
                "timestamp": datetime.fromtimestamp(ts, UTC).date().isoformat(),
                "open": float(quote["open"][idx]),
                "high": float(quote["high"][idx]),
                "low": float(quote["low"][idx]),
                "close": float(close),
                "volume": float(quote["volume"][idx] or 0),
            }
        )
    return bars


def fetch_free_equity_daily(symbol: str, start: str, end: str) -> tuple[str, list[dict]]:
    bars = fetch_stooq_daily(symbol, start, end)
    if bars:
        return "stooq", bars
    return "yahoo-chart", fetch_yahoo_chart_daily(symbol, start, end)


def run_backtest(
    bars: list[dict],
    initial_cash: float = 10_000.0,
    max_notional: float = 5_000.0,
) -> dict:
    cash = initial_cash
    qty = 0
    entry = 0.0
    trades: list[dict] = []
    equity_curve: list[float] = []

    for index, bar in enumerate(bars):
        price = float(bar["close"])
        history = bars[: index + 1]
        decision = decide_signal(history, has_position=qty > 0, entry_price=entry, latest_price=price)

        if decision.action == "buy" and qty == 0 and price > 0:
            qty = max(1, int(min(max_notional, cash) // price))
            if qty > 0:
                cash -= qty * price
                entry = price
                trades.append({"date": bar.get("timestamp"), "action": "buy", "price": price, "qty": qty})
        elif decision.action == "sell" and qty > 0:
            cash += qty * price
            trades.append({"date": bar.get("timestamp"), "action": "sell", "price": price, "qty": qty})
            qty = 0
            entry = 0.0

        equity_curve.append(cash + qty * price)

    final_price = float(bars[-1]["close"]) if bars else 0.0
    final_equity = cash + qty * final_price
    returns = (final_equity / initial_cash - 1) * 100 if initial_cash else 0.0
    max_drawdown = _max_drawdown_pct(equity_curve)
    closed_trades = _closed_trade_pnls(trades)
    wins = [p for p in closed_trades if p > 0]
    losses = [p for p in closed_trades if p <= 0]
    profit_factor = sum(wins) / abs(sum(losses)) if losses and sum(losses) != 0 else math.inf

    return {
        "bars": len(bars),
        "first_date": bars[0].get("timestamp") if bars else "",
        "last_date": bars[-1].get("timestamp") if bars else "",
        "final_equity": round(final_equity, 2),
        "total_return_pct": round(returns, 2),
        "max_drawdown_pct": round(max_drawdown, 2),
        "trades": len(trades),
        "closed_trades": len(closed_trades),
        "win_rate_pct": round(len(wins) / len(closed_trades) * 100, 2) if closed_trades else 0.0,
        "profit_factor": round(profit_factor, 2) if math.isfinite(profit_factor) else "inf",
        "open_qty": qty,
    }


def _closed_trade_pnls(trades: list[dict]) -> list[float]:
    pnls: list[float] = []
    open_trade = None
    for trade in trades:
        if trade["action"] == "buy":
            open_trade = trade
        elif trade["action"] == "sell" and open_trade:
            pnls.append((trade["price"] - open_trade["price"]) * trade["qty"])
            open_trade = None
    return pnls


def _max_drawdown_pct(equity: list[float]) -> float:
    peak = 0.0
    max_dd = 0.0
    for value in equity:
        peak = max(peak, value)
        if peak:
            max_dd = max(max_dd, (peak - value) / peak * 100)
    return max_dd


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--start", default="20160101")
    parser.add_argument("--end", default=datetime.now(UTC).strftime("%Y%m%d"))
    parser.add_argument("--initial-cash", type=float, default=10_000.0)
    parser.add_argument("--max-notional", type=float, default=5_000.0)
    args = parser.parse_args()

    source, bars = fetch_free_equity_daily(args.symbol, args.start, args.end)
    metrics = run_backtest(bars, args.initial_cash, args.max_notional)
    print(f"source: {source}")
    for key, value in metrics.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
