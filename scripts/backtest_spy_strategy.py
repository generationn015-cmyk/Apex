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
import os
import sys
import urllib.request
from datetime import UTC, datetime, time as dt_time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.alpaca_paper_runner import Decision, decide_signal


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


def fetch_alpha_vantage_daily(symbol: str, start: str, end: str) -> list[dict]:
    api_key = os.getenv("ALPHA_VANTAGE_API_KEY", "").strip()
    if not api_key:
        return []
    url = (
        "https://www.alphavantage.co/query"
        f"?function=TIME_SERIES_DAILY_ADJUSTED&symbol={symbol}&outputsize=full&apikey={api_key}"
    )
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    series = payload.get("Time Series (Daily)") or {}
    start_date = datetime.strptime(start, "%Y%m%d").date()
    end_date = datetime.strptime(end, "%Y%m%d").date()
    bars: list[dict] = []
    for day, row in sorted(series.items()):
        current = datetime.strptime(day, "%Y-%m-%d").date()
        if current < start_date or current > end_date:
            continue
        bars.append(
            {
                "timestamp": day,
                "open": float(row["1. open"]),
                "high": float(row["2. high"]),
                "low": float(row["3. low"]),
                "close": float(row["5. adjusted close"]),
                "volume": float(row["6. volume"]),
            }
        )
    return bars


def _dedupe_sorted_bars(bars: list[dict]) -> list[dict]:
    by_date = {bar["timestamp"]: bar for bar in bars if bar.get("timestamp")}
    return [by_date[key] for key in sorted(by_date)]


def fetch_free_equity_daily(
    symbol: str,
    start: str,
    end: str,
    sources: tuple[str, ...] = ("stooq", "yahoo-chart", "alpha-vantage"),
) -> tuple[str, list[dict]]:
    fetchers = {
        "stooq": fetch_stooq_daily,
        "yahoo-chart": fetch_yahoo_chart_daily,
        "alpha-vantage": fetch_alpha_vantage_daily,
    }
    errors: list[str] = []
    for source in sources:
        try:
            bars = fetchers[source](symbol, start, end)
        except Exception as exc:  # noqa: BLE001 - data sources are best-effort research inputs.
            errors.append(f"{source}:{exc.__class__.__name__}")
            continue
        if bars:
            return source, _dedupe_sorted_bars(bars)
    error_note = ",".join(errors) if errors else "no-data"
    return f"unavailable:{error_note}", []


def run_backtest(
    bars: list[dict],
    initial_cash: float = 10_000.0,
    max_notional: float = 5_000.0,
    periods_per_year: int = 252,
) -> dict:
    cash = initial_cash
    qty = 0
    entry = 0.0
    trades: list[dict] = []
    equity_curve: list[float] = []
    invested_periods = 0
    closes: list[float] = []

    for bar in bars:
        price = float(bar["close"])
        if price > 0:
            closes.append(price)
        decision = _decide_from_closes(closes, has_position=qty > 0, entry_price=entry, latest_price=price)

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

        if qty > 0:
            invested_periods += 1
        equity_curve.append(cash + qty * price)

    final_price = float(bars[-1]["close"]) if bars else 0.0
    final_equity = cash + qty * final_price
    returns = (final_equity / initial_cash - 1) * 100 if initial_cash else 0.0
    max_drawdown = _max_drawdown_pct(equity_curve)
    closed_trades = _closed_trade_pnls(trades)
    wins = [p for p in closed_trades if p > 0]
    losses = [p for p in closed_trades if p <= 0]
    profit_factor = sum(wins) / abs(sum(losses)) if losses and sum(losses) != 0 else math.inf
    risk = _risk_adjusted_metrics(equity_curve, bars, initial_cash, max_drawdown, periods_per_year)

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
        "cagr_pct": risk["cagr_pct"],
        "sharpe": risk["sharpe"],
        "sortino": risk["sortino"],
        "calmar": risk["calmar"],
        "exposure_pct": round(invested_periods / len(bars) * 100, 2) if bars else 0.0,
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


def _decide_from_closes(
    closes: list[float],
    has_position: bool,
    entry_price: float,
    latest_price: float,
) -> Decision:
    if len(closes) < 50:
        return decide_signal([{"close": close} for close in closes], has_position, entry_price, latest_price)

    latest = float(latest_price or closes[-1])
    sma20 = sum(closes[-20:]) / 20
    sma50 = sum(closes[-50:]) / 50

    if has_position:
        if entry_price > 0 and latest <= entry_price * 0.98:
            return Decision("sell", "stop_2pct")
        if latest < sma20 and sma20 < sma50:
            return Decision("sell", "trend_break")
        return Decision("hold", "position_protected")

    if latest > sma20 > sma50:
        return Decision("buy", "uptrend")
    return Decision("hold", "no_edge")


def _max_drawdown_pct(equity: list[float]) -> float:
    peak = 0.0
    max_dd = 0.0
    for value in equity:
        peak = max(peak, value)
        if peak:
            max_dd = max(max_dd, (peak - value) / peak * 100)
    return max_dd


def _risk_adjusted_metrics(
    equity: list[float],
    bars: list[dict],
    initial_cash: float,
    max_drawdown_pct: float,
    periods_per_year: int,
) -> dict:
    if not equity or initial_cash <= 0:
        return {"cagr_pct": 0.0, "sharpe": 0.0, "sortino": 0.0, "calmar": 0.0}

    years = _backtest_years(bars, len(equity), periods_per_year)
    final_equity = equity[-1]
    cagr = (final_equity / initial_cash) ** (1 / years) - 1 if years > 0 and final_equity > 0 else 0.0

    returns: list[float] = []
    previous = initial_cash
    for value in equity:
        if previous > 0:
            returns.append((value / previous) - 1)
        previous = value

    sharpe = _annualized_sharpe(returns, periods_per_year)
    downside = [value for value in returns if value < 0]
    sortino = _annualized_sharpe(returns, periods_per_year, downside)
    calmar = cagr / (max_drawdown_pct / 100) if max_drawdown_pct > 0 else 0.0
    return {
        "cagr_pct": round(cagr * 100, 2),
        "sharpe": round(sharpe, 2),
        "sortino": round(sortino, 2),
        "calmar": round(calmar, 2),
    }


def _backtest_years(bars: list[dict], periods: int, periods_per_year: int) -> float:
    first = _parse_timestamp(bars[0].get("timestamp")) if bars else None
    last = _parse_timestamp(bars[-1].get("timestamp")) if bars else None
    if first and last and last > first:
        return max((last - first).days / 365.25, 1 / periods_per_year)
    return max(periods / periods_per_year, 1 / periods_per_year)


def _parse_timestamp(value: object) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError:
            return None


def _annualized_sharpe(
    returns: list[float],
    periods_per_year: int,
    denominator_returns: list[float] | None = None,
) -> float:
    sample = returns[1:] if len(returns) > 1 else returns
    denominator_sample = denominator_returns if denominator_returns is not None else sample
    if len(sample) < 2 or len(denominator_sample) < 2:
        return 0.0
    average = sum(sample) / len(sample)
    variance = sum((value - average) ** 2 for value in denominator_sample) / (len(denominator_sample) - 1)
    deviation = math.sqrt(variance)
    return (average / deviation) * math.sqrt(periods_per_year) if deviation > 0 else 0.0


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
