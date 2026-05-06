"""
Persistent Alpaca paper runner for Apex.

Paper-mode default:
- Paper account only
- Ranked multi-symbol watchlist
- No pyramiding per symbol
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
from datetime import UTC
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
RISK_CYCLE_LOG_PATH = STATE_DIR / "risk_cycle_log.jsonl"
HEARTBEAT_HISTORY_PATH = STATE_DIR / "dashboard_heartbeat_history.json"
MAX_HEARTBEAT_HISTORY = 50
DEFAULT_SYMBOLS = ("SPY", "GOOG", "AAPL", "QQQ", "MS", "XLK", "XLC")
TOP_SIGNAL_REPORT_PATH = STATE_DIR / "top_signal_report.json"
ACTIVE_CANDIDATES_PATH = STATE_DIR / "active_paper_candidates.json"
STRATEGY_RANKINGS_JSON_PATH = STATE_DIR / "strategy_rankings.json"
STRATEGY_RANKINGS_MD_PATH = ROOT / "docs" / "backtests" / "strategy-rankings.md"
NEXT_OPEN_QUEUE_PATH = STATE_DIR / "next_open_queue.json"


def _config_value(name: str, default: str) -> str:
    if os.getenv(name):
        return os.environ[name]
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            if key.strip() == name:
                return value.strip()
    return default


MAX_ACCOUNT_EXPOSURE_PCT = float(_config_value("APEX_ALPACA_MAX_ACCOUNT_EXPOSURE_PCT", "0.45"))
MAX_NEW_BUY_EXPOSURE_PCT = float(_config_value("APEX_ALPACA_MAX_NEW_BUY_EXPOSURE_PCT", "0.05"))
MAX_OPEN_POSITIONS = int(_config_value("APEX_ALPACA_MAX_OPEN_POSITIONS", "7"))
MAX_DAILY_LOSS = float(_config_value("APEX_ALPACA_MAX_DAILY_LOSS", "300.0"))
MAX_OPEN_LOSS = float(_config_value("APEX_ALPACA_MAX_OPEN_LOSS", "300.0"))
MIN_BUYING_POWER_AFTER_TRADE = float(_config_value("APEX_ALPACA_MIN_BUYING_POWER_AFTER_TRADE", "1000.0"))
ROTATION_EXPOSURE_TRIGGER_PCT = float(
    _config_value("APEX_ALPACA_ROTATION_EXPOSURE_TRIGGER_PCT", f"{MAX_ACCOUNT_EXPOSURE_PCT * 0.98:.4f}")
)
PROFIT_ROTATION_PCT = float(_config_value("APEX_ALPACA_PROFIT_ROTATION_PCT", "0.025"))
LAGGARD_ROTATION_LOSS_PCT = float(_config_value("APEX_ALPACA_LAGGARD_ROTATION_LOSS_PCT", "-0.005"))
ENABLE_SHORTS = _config_value("APEX_ALPACA_ENABLE_SHORTS", "0").strip().lower() in {"1", "true", "yes"}
MAX_SHORT_EXPOSURE_PCT = float(_config_value("APEX_ALPACA_MAX_SHORT_EXPOSURE_PCT", "0.12"))
MAX_NEW_SHORT_EXPOSURE_PCT = float(_config_value("APEX_ALPACA_MAX_NEW_SHORT_EXPOSURE_PCT", "0.025"))
MAX_PRESSURE_ROTATIONS_PER_CYCLE = int(_config_value("APEX_ALPACA_MAX_PRESSURE_ROTATIONS_PER_CYCLE", "1"))
ENABLE_REPLACE_TO_ENTER = _config_value("APEX_ALPACA_ENABLE_REPLACE_TO_ENTER", "1").strip().lower() not in {
    "0",
    "false",
    "no",
}
REPLACE_TO_ENTER_MAX_EXIT_PL_PCT = float(_config_value("APEX_ALPACA_REPLACE_TO_ENTER_MAX_EXIT_PL_PCT", "0.008"))
ENFORCE_HISTORICAL_GATES = _config_value("APEX_ALPACA_ENFORCE_HISTORICAL_GATES", "1").strip().lower() not in {"0", "false", "no"}
QUEUE_BUYS_AFTER_CLOSE = _config_value("APEX_ALPACA_QUEUE_BUYS_AFTER_CLOSE", "0").strip().lower() in {"1", "true", "yes"}
MIN_BUY_NOTIONAL = float(_config_value("APEX_ALPACA_MIN_BUY_NOTIONAL", "200.0"))


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
    exposure_pct: float = 0.0
    day_pl: float = 0.0
    unrealized_pl: float = 0.0
    risk_flags: tuple[str, ...] = ()

    @property
    def alerts(self) -> list[str]:
        flags = []
        if self.dry_run:
            flags.append("dry-run")
        if self.equity <= 0:
            flags.append("equity-unavailable")
        if self.position_qty < 0:
            flags.append("short-position")
        flags.extend(self.risk_flags)
        return flags


_HISTORICAL_PASS_CACHE: dict[str, object] = {"mtime": None, "symbols": set()}


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_historical_pass_symbols() -> set[str]:
    """Return symbols that pass the historical gate for paper buys.

    Sources (in priority order):
    - runtime/active_paper_candidates.json (actionable set)
    - runtime/strategy_rankings.json (pass=yes)
    - docs/backtests/strategy-rankings.md (pass=yes)
    """
    # 1) Active candidates (explicit actionable allowlist)
    if ACTIVE_CANDIDATES_PATH.exists():
        payload = _read_json(ACTIVE_CANDIDATES_PATH)
        rows = payload.get("active") or []
        symbols = {str(row.get("symbol", "")).upper() for row in rows if row.get("symbol")}
        if symbols:
            return symbols

    # 2) Strategy rankings JSON
    if STRATEGY_RANKINGS_JSON_PATH.exists():
        payload = _read_json(STRATEGY_RANKINGS_JSON_PATH)
        rows = payload.get("ranked") or []
        symbols = {str(row.get("symbol", "")).upper() for row in rows if row.get("symbol") and bool(row.get("pass"))}
        if symbols:
            return symbols

    # 3) Strategy rankings markdown (fallback for sandboxed/report-only environments)
    if not STRATEGY_RANKINGS_MD_PATH.exists():
        return set()
    mtime = STRATEGY_RANKINGS_MD_PATH.stat().st_mtime
    cached_mtime = _HISTORICAL_PASS_CACHE.get("mtime")
    cached = _HISTORICAL_PASS_CACHE.get("symbols")
    if cached_mtime == mtime and isinstance(cached, set) and cached:
        return cached

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

    _HISTORICAL_PASS_CACHE["mtime"] = mtime
    _HISTORICAL_PASS_CACHE["symbols"] = symbols
    return symbols


def plan_buy_notional(
    desired_notional: float,
    latest_price: float,
    equity: float,
    buying_power: float,
    market_value: float,
) -> float:
    """Plan a buy notional that respects hard caps and practical minimums."""
    if desired_notional <= 0 or latest_price <= 0:
        return 0.0

    notional = min(desired_notional, buying_power)
    if equity > 0:
        notional = min(notional, equity * MAX_NEW_BUY_EXPOSURE_PCT)
        headroom = equity * MAX_ACCOUNT_EXPOSURE_PCT - abs(market_value)
        notional = min(notional, max(0.0, headroom))

    # Must be large enough to buy at least 1 share and clear an absolute floor.
    if notional < max(MIN_BUY_NOTIONAL, latest_price):
        return 0.0
    return float(notional)


def load_next_open_queue() -> list[dict]:
    if not NEXT_OPEN_QUEUE_PATH.exists():
        return []
    payload = _read_json(NEXT_OPEN_QUEUE_PATH)
    items = payload.get("items") if isinstance(payload, dict) else []
    return items if isinstance(items, list) else []


def save_next_open_queue(items: list[dict]) -> None:
    NEXT_OPEN_QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"updated_at": datetime.now(UTC).isoformat(), "items": items}
    NEXT_OPEN_QUEUE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def queue_next_open_sell(symbol: str, qty: int, reason: str) -> None:
    if qty <= 0:
        return
    key = f"SELL:{symbol.upper()}"
    items = load_next_open_queue()
    for item in items:
        if item.get("key") == key:
            item["qty"] = qty
            item["reason"] = reason
            item["queued_at"] = datetime.now(UTC).isoformat()
            save_next_open_queue(items)
            return
    items.append(
        {
            "key": key,
            "symbol": symbol.upper(),
            "side": "sell",
            "qty": int(qty),
            "reason": reason,
            "queued_at": datetime.now(UTC).isoformat(),
        }
    )
    save_next_open_queue(items)


def process_next_open_queue(trading: TradingClient, dry_run: bool) -> int:
    """Submit any queued sells once the market is open (idempotent via position checks + dedupe key)."""
    items = load_next_open_queue()
    if not items:
        return 0

    remaining: list[dict] = []
    processed = 0
    for item in items:
        if item.get("side") != "sell":
            remaining.append(item)
            continue
        symbol = str(item.get("symbol") or "").upper()
        qty = int(float(item.get("qty") or 0))
        if not symbol or qty <= 0:
            continue
        position = get_position(trading, symbol)
        position_qty = int(float(getattr(position, "qty", 0) or 0)) if position is not None else 0
        if position_qty <= 0:
            processed += 1
            if dry_run:
                remaining.append(item)
            continue
        sell_qty = min(position_qty, qty)
        if not dry_run:
            submit_market_order(trading, symbol, OrderSide.SELL, sell_qty)
            logging.info("submitted QUEUED SELL %s qty=%d reason=%s", symbol, sell_qty, item.get("reason"))
        else:
            logging.info("dry-run QUEUED SELL %s qty=%d reason=%s", symbol, sell_qty, item.get("reason"))
            remaining.append(item)
        processed += 1
    if remaining != items:
        save_next_open_queue(remaining)
    return processed


def decide_signal(
    bars: list[dict],
    has_position: bool,
    entry_price: float,
    latest_price: float | None = None,
    exposure_pct: float = 0.0,
    unrealized_pl_pct: float = 0.0,
    position_qty: float = 0.0,
    allow_short: bool = False,
    slot_pressure: bool = False,
    short_pressure: bool = False,
) -> Decision:
    closes = [float(b["close"]) for b in bars if float(b.get("close", 0)) > 0]
    if len(closes) < 50:
        return Decision("hold", "not_enough_bars")

    latest = float(latest_price or closes[-1])
    sma20 = sum(closes[-20:]) / 20
    sma50 = sum(closes[-50:]) / 50

    if position_qty < 0:
        if short_pressure and unrealized_pl_pct >= 0.003:
            return Decision("buy", "short_sleeve_take_profit")
        if short_pressure and unrealized_pl_pct <= -0.003:
            return Decision("buy", "short_sleeve_laggard_cover")
        if entry_price > 0 and latest >= entry_price * 1.02:
            return Decision("buy", "short_stop_2pct")
        if latest > sma20 and sma20 > sma50:
            return Decision("buy", "short_trend_reversal")
        return Decision("hold", "short_position_protected")

    if has_position:
        if slot_pressure and unrealized_pl_pct >= 0.01:
            return Decision("sell", "slot_pressure_take_profit")
        if slot_pressure and unrealized_pl_pct <= 0 and latest < sma20:
            return Decision("sell", "slot_pressure_laggard")
        if exposure_pct >= ROTATION_EXPOSURE_TRIGGER_PCT and unrealized_pl_pct >= PROFIT_ROTATION_PCT:
            return Decision("sell", "rotation_take_profit")
        if (
            exposure_pct >= ROTATION_EXPOSURE_TRIGGER_PCT
            and unrealized_pl_pct <= LAGGARD_ROTATION_LOSS_PCT
            and latest < sma20
        ):
            return Decision("sell", "rotation_laggard")
        if entry_price > 0 and latest <= entry_price * 0.98:
            return Decision("sell", "stop_2pct")
        if latest < sma20 and sma20 < sma50:
            return Decision("sell", "trend_break")
        return Decision("hold", "position_protected")

    if latest > sma20 > sma50:
        return Decision("buy", "uptrend")
    if allow_short and latest < sma20 < sma50:
        return Decision("sell", "short_downtrend")
    return Decision("hold", "no_edge")


def evaluate_risk(
    equity: float,
    buying_power: float,
    market_value: float,
    day_pl: float,
    unrealized_pl: float,
    pending_buy_notional: float = 0.0,
    pending_short_notional: float = 0.0,
    short_market_value: float = 0.0,
    open_position_count: int = 0,
) -> list[str]:
    flags: list[str] = []
    exposure_pct = abs(market_value) / equity if equity else 1.0
    projected_exposure_pct = (abs(market_value) + max(pending_buy_notional, 0.0)) / equity if equity else 1.0
    pending_exposure_pct = max(pending_buy_notional, 0.0) / equity if equity else 1.0
    projected_short_exposure_pct = (
        (abs(short_market_value) + max(pending_short_notional, 0.0)) / equity if equity else 1.0
    )
    pending_short_exposure_pct = max(pending_short_notional, 0.0) / equity if equity else 1.0
    if exposure_pct > MAX_ACCOUNT_EXPOSURE_PCT:
        flags.append(f"exposure-over-{MAX_ACCOUNT_EXPOSURE_PCT:.0%}")
    if pending_buy_notional > 0 and projected_exposure_pct > MAX_ACCOUNT_EXPOSURE_PCT:
        flags.append(f"projected-exposure-over-{MAX_ACCOUNT_EXPOSURE_PCT:.0%}")
    if pending_buy_notional > 0 and pending_exposure_pct > MAX_NEW_BUY_EXPOSURE_PCT:
        flags.append(f"new-buy-exposure-over-{MAX_NEW_BUY_EXPOSURE_PCT:.0%}")
    if pending_buy_notional > 0 and open_position_count >= MAX_OPEN_POSITIONS:
        flags.append("max-open-positions")
    if day_pl <= -MAX_DAILY_LOSS:
        flags.append("daily-loss-over-300")
    if unrealized_pl <= -MAX_OPEN_LOSS:
        flags.append("open-loss-over-300")
    if pending_buy_notional > 0 and buying_power - pending_buy_notional < MIN_BUYING_POWER_AFTER_TRADE:
        flags.append("buying-power-buffer-low")
    if short_market_value > 0 and abs(short_market_value) / equity > MAX_SHORT_EXPOSURE_PCT:
        flags.append(f"short-exposure-over-{MAX_SHORT_EXPOSURE_PCT:.0%}")
    if pending_short_notional > 0 and projected_short_exposure_pct > MAX_SHORT_EXPOSURE_PCT:
        flags.append(f"projected-short-exposure-over-{MAX_SHORT_EXPOSURE_PCT:.0%}")
    if pending_short_notional > 0 and pending_short_exposure_pct > MAX_NEW_SHORT_EXPOSURE_PCT:
        flags.append(f"new-short-exposure-over-{MAX_NEW_SHORT_EXPOSURE_PCT:.1%}")
    return flags


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


def get_positions_by_symbol(trading: TradingClient) -> dict[str, object]:
    try:
        positions = trading.get_all_positions()
    except Exception:
        positions = []
    return {str(position.symbol).upper(): position for position in positions}


def total_market_value(positions: dict[str, object]) -> float:
    return sum(abs(float(getattr(position, "market_value", 0) or 0)) for position in positions.values())


def total_short_market_value(positions: dict[str, object]) -> float:
    total = 0.0
    for position in positions.values():
        qty = float(getattr(position, "qty", 0) or 0)
        if qty < 0:
            total += abs(float(getattr(position, "market_value", 0) or 0))
    return total


def _position_unrealized_pl_pct(position: object) -> float:
    try:
        return float(getattr(position, "unrealized_plpc", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def pressure_rotation_symbol(positions: dict[str, object]) -> str | None:
    long_positions = [
        position
        for position in positions.values()
        if float(getattr(position, "qty", 0) or 0) > 0
    ]
    if not long_positions:
        return None
    laggards = [position for position in long_positions if _position_unrealized_pl_pct(position) <= 0]
    if laggards:
        pick = min(laggards, key=_position_unrealized_pl_pct)
        return str(getattr(pick, "symbol", "")).upper() or None
    winners = [position for position in long_positions if _position_unrealized_pl_pct(position) >= 0.01]
    if winners:
        pick = max(winners, key=_position_unrealized_pl_pct)
        return str(getattr(pick, "symbol", "")).upper() or None
    return None


def short_pressure_rotation_symbol(positions: dict[str, object]) -> str | None:
    short_positions = [
        position
        for position in positions.values()
        if float(getattr(position, "qty", 0) or 0) < 0
    ]
    if not short_positions:
        return None
    profitable = [position for position in short_positions if _position_unrealized_pl_pct(position) >= 0.003]
    if profitable:
        pick = max(profitable, key=_position_unrealized_pl_pct)
        return str(getattr(pick, "symbol", "")).upper() or None
    laggards = [position for position in short_positions if _position_unrealized_pl_pct(position) <= -0.003]
    if laggards:
        pick = min(laggards, key=_position_unrealized_pl_pct)
        return str(getattr(pick, "symbol", "")).upper() or None
    return None


def replace_to_enter_exit_symbol(
    positions: dict[str, object],
    *,
    exclude_symbol: str = "",
    max_exit_pl_pct: float = REPLACE_TO_ENTER_MAX_EXIT_PL_PCT,
) -> str | None:
    exclude = exclude_symbol.upper()
    candidates = [
        position
        for position in positions.values()
        if float(getattr(position, "qty", 0) or 0) > 0
        and str(getattr(position, "symbol", "")).upper() != exclude
        and _position_unrealized_pl_pct(position) <= max_exit_pl_pct
    ]
    if not candidates:
        return None
    pick = min(candidates, key=_position_unrealized_pl_pct)
    return str(getattr(pick, "symbol", "")).upper() or None


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


def append_risk_cycle(payload: dict) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    payload = {**payload, "timestamp": datetime.now(UTC).isoformat()}
    with RISK_CYCLE_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, separators=(",", ":")) + "\n")


def run_once(
    symbol: str,
    max_notional: float,
    dry_run: bool,
    *,
    env: dict[str, str] | None = None,
    trading: TradingClient | None = None,
    data: StockHistoricalDataClient | None = None,
    allow_pressure_rotation: bool = True,
) -> RunnerResult:
    env = env or load_env()
    if trading is None or data is None:
        trading, data = get_clients(env)
    account = trading.get_account()
    clock = trading.get_clock()
    positions = get_positions_by_symbol(trading)
    position = positions.get(symbol.upper())
    bars = fetch_bars(data, symbol, limit=100)

    position_qty = float(getattr(position, "qty", 0) or 0)
    has_long_position = position is not None and position_qty > 0
    has_short_position = position is not None and position_qty < 0
    has_position = has_long_position
    entry_price = float(position.avg_entry_price) if position is not None else 0.0
    latest = _position_price(position) if position is not None else (bars[-1]["close"] if bars else 0.0)
    equity = float(account.portfolio_value)
    buying_power = float(account.buying_power)
    last_equity = float(getattr(account, "last_equity", 0) or 0)
    day_pl = equity - last_equity if last_equity else 0.0
    market_value = total_market_value(positions)
    short_market_value = total_short_market_value(positions)
    unrealized_pl = float(getattr(position, "unrealized_pl", 0) or 0)
    unrealized_pl_pct = float(getattr(position, "unrealized_plpc", 0) or 0)
    exposure_pct = market_value / equity if equity else 1.0
    slot_pressure_symbol = pressure_rotation_symbol(positions) if len(positions) > MAX_OPEN_POSITIONS else None
    short_pressure_symbol = (
        short_pressure_rotation_symbol(positions)
        if short_market_value > 0 and equity > 0 and short_market_value / equity > MAX_SHORT_EXPOSURE_PCT
        else None
    )
    slot_pressure = allow_pressure_rotation and symbol.upper() == slot_pressure_symbol
    short_pressure = (
        allow_pressure_rotation
        and symbol.upper() == short_pressure_symbol
    )
    decision = decide_signal(
        bars,
        has_position=has_position,
        entry_price=entry_price,
        latest_price=latest,
        exposure_pct=exposure_pct,
        unrealized_pl_pct=unrealized_pl_pct,
        position_qty=position_qty,
        allow_short=ENABLE_SHORTS,
        slot_pressure=slot_pressure,
        short_pressure=short_pressure,
    )

    historical_pass = load_historical_pass_symbols()
    enforce_gate = ENFORCE_HISTORICAL_GATES and bool(historical_pass)
    if decision.action == "buy" and position is None and enforce_gate and symbol.upper() not in historical_pass:
        decision = Decision("hold", "risk_block:historical-gate-fail")

    desired_buy_notional = max_notional if decision.action == "buy" and position is None else 0.0
    pending_buy_notional = plan_buy_notional(
        desired_notional=desired_buy_notional,
        latest_price=float(latest or 0),
        equity=equity,
        buying_power=buying_power,
        market_value=market_value,
    )
    pending_short_notional = 0.0
    if decision.action == "sell" and position is None and ENABLE_SHORTS:
        pending_short_notional = min(max_notional, buying_power)
        if equity > 0:
            pending_short_notional = min(
                pending_short_notional,
                equity * MAX_NEW_SHORT_EXPOSURE_PCT,
                max(0.0, equity * MAX_SHORT_EXPOSURE_PCT - short_market_value),
            )
        if latest <= 0 or pending_short_notional < max(MIN_BUY_NOTIONAL, latest):
            decision = Decision("hold", "risk_block:short-headroom-low")
            pending_short_notional = 0.0
    if decision.action == "buy" and position is None and desired_buy_notional > 0 and pending_buy_notional <= 0:
        decision = Decision("hold", "risk_block:cap-headroom-low")
    risk_flags = evaluate_risk(
        equity=equity,
        buying_power=buying_power,
        market_value=market_value,
        day_pl=day_pl,
        unrealized_pl=unrealized_pl,
        pending_buy_notional=pending_buy_notional,
        pending_short_notional=pending_short_notional,
        short_market_value=short_market_value,
        open_position_count=len(positions),
    )
    replacement_exit_symbol = None
    replacement_entry_notional = 0.0
    if (
        ENABLE_REPLACE_TO_ENTER
        and allow_pressure_rotation
        and decision.action == "buy"
        and position is None
        and "max-open-positions" in risk_flags
    ):
        replacement_exit_symbol = replace_to_enter_exit_symbol(positions, exclude_symbol=symbol)
        if replacement_exit_symbol:
            replacement_entry_notional = pending_buy_notional
            decision = Decision("hold", f"replace_to_enter:{symbol.upper()}_free:{replacement_exit_symbol}")
            pending_buy_notional = 0.0

    if decision.action == "buy" and not has_short_position and risk_flags:
        decision = Decision("hold", "risk_block:" + ",".join(risk_flags))
    if decision.action == "sell" and not has_long_position and risk_flags:
        short_flags = [flag for flag in risk_flags if "short" in flag or flag in {"max-open-positions", "buying-power-buffer-low"}]
        if short_flags:
            decision = Decision("hold", "risk_block:" + ",".join(short_flags))

    projected_exposure_pct = (
        (abs(market_value) + max(pending_buy_notional, 0.0) + max(pending_short_notional, 0.0)) / equity
        if equity
        else 1.0
    )
    append_risk_cycle(
        {
            "symbol": symbol.upper(),
            "market_open": bool(clock.is_open),
            "dry_run": bool(dry_run),
            "decision": decision.action,
            "reason": decision.reason,
            "equity": round(equity, 2),
            "buying_power": round(buying_power, 2),
            "open_position_count": len(positions),
            "market_value": round(market_value, 2),
            "exposure_pct": round(exposure_pct, 6),
            "projected_exposure_pct": round(projected_exposure_pct, 6),
            "pending_buy_notional": round(pending_buy_notional, 2),
            "pending_short_notional": round(pending_short_notional, 2),
            "slot_pressure": bool(slot_pressure),
            "short_pressure": bool(short_pressure),
            "slot_pressure_symbol": slot_pressure_symbol,
            "short_pressure_symbol": short_pressure_symbol,
            "replacement_exit_symbol": replacement_exit_symbol,
            "replacement_entry_notional": round(replacement_entry_notional, 2),
            "caps": {
                "max_account_exposure_pct": MAX_ACCOUNT_EXPOSURE_PCT,
                "max_new_buy_exposure_pct": MAX_NEW_BUY_EXPOSURE_PCT,
                "max_short_exposure_pct": MAX_SHORT_EXPOSURE_PCT,
                "max_new_short_exposure_pct": MAX_NEW_SHORT_EXPOSURE_PCT,
                "max_open_positions": MAX_OPEN_POSITIONS,
                "max_pressure_rotations_per_cycle": MAX_PRESSURE_ROTATIONS_PER_CYCLE,
                "replace_to_enter_max_exit_pl_pct": REPLACE_TO_ENTER_MAX_EXIT_PL_PCT,
            },
        }
    )

    logging.info(
        "symbol=%s action=%s reason=%s market_open=%s equity=%s buying_power=%s position=%s latest=%.2f",
        symbol,
        decision.action,
        decision.reason,
        clock.is_open,
        equity,
        buying_power,
        getattr(position, "qty", 0),
        latest,
    )
    append_journal(
        path=JOURNAL_PATH,
        symbol=symbol,
        action=decision.action,
        reason=decision.reason,
        market_open=bool(clock.is_open),
        equity=equity,
        buying_power=buying_power,
        position_qty=position_qty,
        latest_price=latest,
        dry_run=dry_run,
    )

    result = RunnerResult(
        symbol=symbol,
        decision=decision,
        market_open=bool(clock.is_open),
        equity=equity,
        buying_power=buying_power,
        position_qty=position_qty,
        latest_price=latest,
        dry_run=dry_run,
        exposure_pct=exposure_pct,
        day_pl=day_pl,
        unrealized_pl=unrealized_pl,
        risk_flags=tuple(risk_flags),
    )

    if dry_run:
        return result

    if not clock.is_open:
        if decision.reason.startswith("replace_to_enter:") and replacement_exit_symbol:
            replacement_position = positions.get(replacement_exit_symbol)
            replacement_qty = int(float(getattr(replacement_position, "qty", 0) or 0)) if replacement_position else 0
            if replacement_qty > 0:
                queue_next_open_sell(replacement_exit_symbol, replacement_qty, decision.reason)
                logging.info(
                    "queued REPLACE-TO-ENTER SELL %s qty=%d reason=%s",
                    replacement_exit_symbol,
                    replacement_qty,
                    decision.reason,
                )
        if decision.action == "sell" and has_long_position:
            queue_next_open_sell(symbol, int(float(position.qty)), decision.reason)
            logging.info("queued SELL %s qty=%s reason=%s", symbol, position.qty, decision.reason)
        return result

    if decision.reason.startswith("replace_to_enter:") and replacement_exit_symbol:
        replacement_position = positions.get(replacement_exit_symbol)
        replacement_qty = int(float(getattr(replacement_position, "qty", 0) or 0)) if replacement_position else 0
        if replacement_qty > 0:
            submit_market_order(trading, replacement_exit_symbol, OrderSide.SELL, replacement_qty)
            logging.info(
                "submitted REPLACE-TO-ENTER SELL %s qty=%d target=%s",
                replacement_exit_symbol,
                replacement_qty,
                symbol.upper(),
            )
        entry_qty = int(replacement_entry_notional // latest) if latest > 0 else 0
        if entry_qty > 0:
            submit_market_order(trading, symbol, OrderSide.BUY, entry_qty)
            logging.info(
                "submitted REPLACE-TO-ENTER BUY %s qty=%d notional=%.2f",
                symbol.upper(),
                entry_qty,
                replacement_entry_notional,
            )
    elif decision.action == "buy" and has_short_position:
        qty = abs(int(position_qty))
        if qty > 0:
            submit_market_order(trading, symbol, OrderSide.BUY, qty)
            logging.info("submitted COVER %s qty=%d", symbol, qty)
    elif decision.action == "buy" and position is None:
        qty = int(pending_buy_notional // latest) if latest > 0 else 0
        if qty > 0:
            submit_market_order(trading, symbol, OrderSide.BUY, qty)
            logging.info("submitted BUY %s qty=%d notional=%.2f", symbol, qty, pending_buy_notional)
    elif decision.action == "sell" and has_long_position:
        qty = int(float(position.qty))
        if qty > 0:
            submit_market_order(trading, symbol, OrderSide.SELL, qty)
            logging.info("submitted SELL %s qty=%d", symbol, qty)
    elif decision.action == "sell" and position is None and ENABLE_SHORTS:
        qty = int(pending_short_notional // latest) if latest > 0 else 0
        if qty > 0:
            submit_market_order(trading, symbol, OrderSide.SELL, qty)
            logging.info("submitted SHORT %s qty=%d notional=%.2f", symbol, qty, pending_short_notional)

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
        "risk": {
            "exposure_pct": result.exposure_pct,
            "day_pl": result.day_pl,
            "unrealized_pl": result.unrealized_pl,
            "flags": list(result.risk_flags),
            "max_account_exposure_pct": MAX_ACCOUNT_EXPOSURE_PCT,
            "max_new_buy_exposure_pct": MAX_NEW_BUY_EXPOSURE_PCT,
        },
        "signals": load_top_signal_summary(),
    }
    history = save_dashboard_heartbeat_history(heartbeat)
    payload = json.dumps({**heartbeat, "history": [compact_heartbeat(item) for item in history[-12:]]}).encode("utf-8")
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


def compact_heartbeat(heartbeat: dict) -> dict:
    return {
        "timestamp": heartbeat.get("timestamp"),
        "symbol": heartbeat.get("symbol"),
        "decision": heartbeat.get("decision"),
        "reason": heartbeat.get("reason"),
        "market_open": heartbeat.get("market_open"),
        "equity": heartbeat.get("equity"),
        "buying_power": heartbeat.get("buying_power"),
        "position_qty": heartbeat.get("position_qty"),
        "latest_price": heartbeat.get("latest_price"),
        "dry_run": heartbeat.get("dry_run"),
        "alerts": heartbeat.get("alerts") or [],
    }


def load_top_signal_summary() -> dict:
    if not TOP_SIGNAL_REPORT_PATH.exists():
        return {}
    try:
        payload = json.loads(TOP_SIGNAL_REPORT_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    rows = payload.get("signals") or []
    actionable = [row for row in rows if row.get("actionable")]
    return {
        "generated_at": payload.get("generated_at"),
        "actionable_count": len(actionable),
        "top": [
            {
                "symbol": row.get("symbol"),
                "decision": row.get("decision"),
                "reason": row.get("reason"),
                "actionable": bool(row.get("actionable")),
                "score": row.get("score"),
                "latest_price": row.get("latest_price"),
                "full": {
                    "sharpe": (row.get("full") or {}).get("sharpe"),
                    "calmar": (row.get("full") or {}).get("calmar"),
                    "cagr_pct": (row.get("full") or {}).get("cagr_pct"),
                },
                "recent_3y": {
                    "total_return_pct": (row.get("recent_3y") or {}).get("total_return_pct"),
                    "max_drawdown_pct": (row.get("recent_3y") or {}).get("max_drawdown_pct"),
                    "sharpe": (row.get("recent_3y") or {}).get("sharpe"),
                    "calmar": (row.get("recent_3y") or {}).get("calmar"),
                },
            }
            for row in rows[:5]
        ],
    }


def parse_symbols(value: str) -> list[str]:
    symbols = []
    for item in value.split(","):
        symbol = item.strip().upper()
        if symbol and symbol not in symbols:
            symbols.append(symbol)
    return symbols


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
    parser.add_argument("--symbol", default=os.getenv("APEX_ALPACA_SYMBOL", ""))
    parser.add_argument(
        "--symbols",
        default=os.getenv("APEX_ALPACA_SYMBOLS", ",".join(DEFAULT_SYMBOLS)),
        help="Comma-separated paper symbols to evaluate each cycle.",
    )
    parser.add_argument("--max-notional", type=float, default=float(os.getenv("APEX_ALPACA_MAX_NOTIONAL", "5000")))
    parser.add_argument("--interval", type=int, default=int(os.getenv("APEX_ALPACA_INTERVAL_SEC", "300")))
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    setup_logging()
    symbols = parse_symbols(args.symbols)
    if args.symbol:
        symbols = parse_symbols(args.symbol)
    if not symbols:
        symbols = list(DEFAULT_SYMBOLS)

    logging.info("Apex Alpaca paper runner starting symbols=%s dry_run=%s", ",".join(symbols), args.dry_run)

    while True:
        env = load_env()
        try:
            trading, data = get_clients(env)
            clock = trading.get_clock()
            if clock.is_open:
                processed = process_next_open_queue(trading, args.dry_run)
                if processed:
                    logging.info("processed next-open queue count=%d", processed)
            pressure_rotations = 0
            for symbol in symbols:
                result = run_once(
                    symbol,
                    args.max_notional,
                    args.dry_run,
                    env=env,
                    trading=trading,
                    data=data,
                    allow_pressure_rotation=pressure_rotations < MAX_PRESSURE_ROTATIONS_PER_CYCLE,
                )
                if result.decision.reason in {
                    "slot_pressure_take_profit",
                    "slot_pressure_laggard",
                    "short_sleeve_take_profit",
                    "short_sleeve_laggard_cover",
                }:
                    pressure_rotations += 1
                if result.decision.reason.startswith("replace_to_enter:"):
                    pressure_rotations += 1
                write_heartbeat(",".join(symbols))
                publish_dashboard_heartbeat(env, result)
        except Exception as exc:
            logging.exception("runner cycle failed: %s", exc)
        if args.once:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
