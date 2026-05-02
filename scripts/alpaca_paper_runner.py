"""
Persistent Alpaca paper runner for Apex.

Conservative default:
- Paper account only
- SPY only
- No pyramiding
- Buy only when trend is up and no position exists
- Sell only on stop or trend break
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest


ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs"
STATE_DIR = ROOT / "runtime"
JOURNAL_PATH = ROOT / "data" / "paper_journal.csv"
HEARTBEAT_HISTORY_PATH = STATE_DIR / "dashboard_heartbeat_history.json"
MAX_HEARTBEAT_HISTORY = 50


@dataclass(frozen=True)
class Decision:
    action: str
    reason: str


@dataclass(frozen=True)
class RunnerResult:
    symbol: str
    decision: Decision
    market_open: bool
    equity: float
    buying_power: float
    position_qty: float
    latest_price: float
    dry_run: bool

    @property
    def alerts(self) -> list[str]:
        flags = []
        if self.dry_run:
            flags.append("dry-run")
        if self.equity <= 0:
            flags.append("equity-unavailable")
        if self.position_qty < 0:
            flags.append("short-position")
        return flags


def decide_signal(
    bars: list[dict],
    has_position: bool,
    entry_price: float,
    latest_price: float | None = None,
) -> Decision:
    closes = [float(b["close"]) for b in bars if float(b.get("close", 0)) > 0]
    if len(closes) < 50:
        return Decision("hold", "not_enough_bars")

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


def load_env() -> dict[str, str]:
    values = dict(os.environ)
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def setup_logging() -> None:
    LOG_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(LOG_DIR / "alpaca_paper_runner.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def get_clients(env: dict[str, str]) -> tuple[TradingClient, StockHistoricalDataClient]:
    key = env.get("APCA_API_KEY_ID", "")
    secret = env.get("APCA_API_SECRET_KEY", "")
    if not key or not secret:
        raise RuntimeError("Missing APCA_API_KEY_ID/APCA_API_SECRET_KEY in .env")
    return TradingClient(key, secret, paper=True), StockHistoricalDataClient(key, secret)


def fetch_bars(data: StockHistoricalDataClient, symbol: str, limit: int = 80) -> list[dict]:
    request = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame(1, TimeFrameUnit.Day),
        start=datetime.now(timezone.utc) - timedelta(days=140),
        limit=limit,
        feed="iex",
    )
    result = data.get_stock_bars(request)
    records = list(result.data.get(symbol, []))
    return [
        {
            "timestamp": bar.timestamp,
            "open": float(bar.open),
            "high": float(bar.high),
            "low": float(bar.low),
            "close": float(bar.close),
            "volume": float(bar.volume),
        }
        for bar in records
    ]


def get_position(trading: TradingClient, symbol: str):
    try:
        return trading.get_open_position(symbol)
    except Exception:
        return None


def submit_market_order(trading: TradingClient, symbol: str, side: OrderSide, qty: int):
    request = MarketOrderRequest(
        symbol=symbol,
        qty=qty,
        side=side,
        time_in_force=TimeInForce.DAY,
    )
    return trading.submit_order(order_data=request)


def append_journal(
    path: Path,
    symbol: str,
    action: str,
    reason: str,
    market_open: bool,
    equity: float,
    buying_power: float,
    position_qty: float,
    latest_price: float,
    dry_run: bool,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(
                [
                    "timestamp",
                    "symbol",
                    "action",
                    "reason",
                    "market_open",
                    "equity",
                    "buying_power",
                    "position_qty",
                    "latest_price",
                    "dry_run",
                ]
            )
        writer.writerow(
            [
                datetime.now(timezone.utc).isoformat(),
                symbol,
                action,
                reason,
                market_open,
                f"{equity:.2f}",
                f"{buying_power:.2f}",
                f"{position_qty:.6f}",
                f"{latest_price:.4f}",
                dry_run,
            ]
        )


def run_once(symbol: str, max_notional: float, dry_run: bool) -> RunnerResult:
    env = load_env()
    trading, data = get_clients(env)
    account = trading.get_account()
    clock = trading.get_clock()
    position = get_position(trading, symbol)
    bars = fetch_bars(data, symbol)

    has_position = position is not None and float(position.qty) > 0
    entry_price = float(position.avg_entry_price) if has_position else 0.0
    latest = _position_price(position) if position is not None else (bars[-1]["close"] if bars else 0.0)
    decision = decide_signal(
        bars,
        has_position=has_position,
        entry_price=entry_price,
        latest_price=latest,
    )

    logging.info(
        "symbol=%s action=%s reason=%s market_open=%s equity=%s buying_power=%s position=%s latest=%.2f",
        symbol,
        decision.action,
        decision.reason,
        clock.is_open,
        account.portfolio_value,
        account.buying_power,
        getattr(position, "qty", 0),
        latest,
    )
    append_journal(
        path=JOURNAL_PATH,
        symbol=symbol,
        action=decision.action,
        reason=decision.reason,
        market_open=bool(clock.is_open),
        equity=float(account.portfolio_value),
        buying_power=float(account.buying_power),
        position_qty=float(getattr(position, "qty", 0) or 0),
        latest_price=latest,
        dry_run=dry_run,
    )

    result = RunnerResult(
        symbol=symbol,
        decision=decision,
        market_open=bool(clock.is_open),
        equity=float(account.portfolio_value),
        buying_power=float(account.buying_power),
        position_qty=float(getattr(position, "qty", 0) or 0),
        latest_price=latest,
        dry_run=dry_run,
    )

    if dry_run:
        return result
    if not clock.is_open:
        return result

    if decision.action == "buy" and not has_position:
        qty = max(1, int(max_notional // latest))
        submit_market_order(trading, symbol, OrderSide.BUY, qty)
        logging.info("submitted BUY %s qty=%d", symbol, qty)
    elif decision.action == "sell" and has_position:
        qty = int(float(position.qty))
        if qty > 0:
            submit_market_order(trading, symbol, OrderSide.SELL, qty)
            logging.info("submitted SELL %s qty=%d", symbol, qty)

    return result


def write_heartbeat(symbol: str) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    (STATE_DIR / "alpaca_paper_runner.heartbeat").write_text(
        f"{datetime.now(timezone.utc).isoformat()} {symbol}\n",
        encoding="utf-8",
    )


def publish_dashboard_heartbeat(env: dict[str, str], result: RunnerResult) -> None:
    url = env.get("APEX_DASHBOARD_HEARTBEAT_URL", "").strip()
    token = env.get("APEX_HEARTBEAT_TOKEN", "").strip() or env.get("APEX_DASHBOARD_TOKEN", "").strip()
    if not url or not token:
        return
    heartbeat = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "symbol": result.symbol,
        "decision": result.decision.action,
        "reason": result.decision.reason,
        "market_open": result.market_open,
        "equity": result.equity,
        "buying_power": result.buying_power,
        "position_qty": result.position_qty,
        "latest_price": result.latest_price,
        "dry_run": result.dry_run,
        "alerts": result.alerts,
    }
    history = save_dashboard_heartbeat_history(heartbeat)
    payload = json.dumps({**heartbeat, "history": history[-12:]}).encode("utf-8")
    request = Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-Apex-Heartbeat-Token": token,
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=8):
            logging.info("published dashboard heartbeat")
    except Exception as exc:
        logging.warning("dashboard heartbeat publish failed: %s", exc)


def save_dashboard_heartbeat_history(heartbeat: dict) -> list[dict]:
    STATE_DIR.mkdir(exist_ok=True)
    history: list[dict] = []
    if HEARTBEAT_HISTORY_PATH.exists():
        try:
            loaded = json.loads(HEARTBEAT_HISTORY_PATH.read_text(encoding="utf-8"))
            history = loaded if isinstance(loaded, list) else []
        except json.JSONDecodeError:
            history = []
    history.append(heartbeat)
    history = history[-MAX_HEARTBEAT_HISTORY:]
    HEARTBEAT_HISTORY_PATH.write_text(json.dumps(history, indent=2), encoding="utf-8")
    return history


def _position_price(position) -> float:
    for attr in ("current_price", "market_value"):
        value = getattr(position, attr, None)
        if value not in (None, ""):
            numeric = float(value)
            if attr == "market_value":
                qty = abs(float(getattr(position, "qty", 0) or 0))
                return numeric / qty if qty else 0.0
            return numeric
    return 0.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default=os.getenv("APEX_ALPACA_SYMBOL", "SPY"))
    parser.add_argument("--max-notional", type=float, default=float(os.getenv("APEX_ALPACA_MAX_NOTIONAL", "5000")))
    parser.add_argument("--interval", type=int, default=int(os.getenv("APEX_ALPACA_INTERVAL_SEC", "300")))
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    setup_logging()
    logging.info("Apex Alpaca paper runner starting symbol=%s dry_run=%s", args.symbol, args.dry_run)

    while True:
        env = load_env()
        try:
            result = run_once(args.symbol, args.max_notional, args.dry_run)
            write_heartbeat(args.symbol)
            publish_dashboard_heartbeat(env, result)
        except Exception as exc:
            logging.exception("runner cycle failed: %s", exc)
        if args.once:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
