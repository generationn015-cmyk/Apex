import json
import os
import tempfile
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlencode
from urllib.request import Request, urlopen


PAPER_ENDPOINT = "https://paper-api.alpaca.markets"
HEARTBEAT_PATH = os.path.join(tempfile.gettempdir(), "apex_runner_heartbeat.json")


def _dashboard_token():
    return os.getenv("APEX_DASHBOARD_TOKEN") or os.getenv("DASHBOARD_ACCESS_TOKEN")


def _headers():
    key = os.getenv("APCA_API_KEY_ID") or os.getenv("ALPACA_API_KEY")
    secret = os.getenv("APCA_API_SECRET_KEY") or os.getenv("ALPACA_API_SECRET")
    if not key or not secret:
        return None
    return {
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
        "Accept": "application/json",
    }


def _get(path, params=None):
    headers = _headers()
    if not headers:
        raise RuntimeError("Alpaca paper credentials are not configured in Vercel.")
    query = f"?{urlencode(params)}" if params else ""
    req = Request(f"{PAPER_ENDPOINT}{path}{query}", headers=headers, method="GET")
    with urlopen(req, timeout=12) as res:
        return json.loads(res.read().decode("utf-8"))


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _optional_get(path, params=None, fallback=None):
    try:
        return _get(path, params)
    except Exception:
        return fallback


def _runner_heartbeat():
    if not os.path.exists(HEARTBEAT_PATH):
        return {
            "status": "external-watchdog",
            "visible_from_vercel": False,
            "stale": True,
            "note": "Waiting for the local watchdog heartbeat relay.",
        }
    try:
        with open(HEARTBEAT_PATH, "r", encoding="utf-8") as f:
            heartbeat = json.load(f)
        timestamp = heartbeat.get("timestamp")
        age_seconds = None
        stale = True
        if timestamp:
            age_seconds = int(
                (
                    datetime.now(timezone.utc)
                    - datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                ).total_seconds()
            )
            stale = age_seconds > 600
        return {
            "status": "relay-visible",
            "visible_from_vercel": True,
            "stale": stale,
            "age_seconds": age_seconds,
            "symbol": heartbeat.get("symbol"),
            "latest_decision": heartbeat.get("decision"),
            "latest_reason": heartbeat.get("reason"),
            "last_seen": timestamp,
            "note": "Best-effort Vercel relay from the local Windows watchdog.",
        }
    except Exception:
        return {
            "status": "relay-unreadable",
            "visible_from_vercel": False,
            "stale": True,
            "note": "Heartbeat relay file exists but could not be parsed.",
        }


def _status_payload():
    account = _get("/v2/account")
    positions = _get("/v2/positions")
    orders = _get(
        "/v2/orders",
        {"status": "all", "limit": 10, "direction": "desc", "nested": "false"},
    )
    clock = _get("/v2/clock")
    history = _optional_get(
        "/v2/account/portfolio/history",
        {"period": "1M", "timeframe": "1D", "intraday_reporting": "market_hours"},
        {"timestamp": [], "equity": [], "profit_loss": [], "profit_loss_pct": []},
    )

    equity = _safe_float(account.get("equity") or account.get("portfolio_value"))
    last_equity = _safe_float(account.get("last_equity"))
    day_pl = equity - last_equity if last_equity else 0.0

    clean_positions = []
    unrealized_total = 0.0
    market_value_total = 0.0
    for item in positions:
        pl = _safe_float(item.get("unrealized_pl"))
        market_value = abs(_safe_float(item.get("market_value")))
        unrealized_total += pl
        market_value_total += market_value
        clean_positions.append(
            {
                "symbol": item.get("symbol"),
                "qty": item.get("qty"),
                "side": item.get("side"),
                "avg_entry_price": item.get("avg_entry_price"),
                "current_price": item.get("current_price"),
                "market_value": item.get("market_value"),
                "unrealized_pl": item.get("unrealized_pl"),
                "unrealized_plpc": item.get("unrealized_plpc"),
            }
        )

    clean_orders = []
    for item in orders:
        clean_orders.append(
            {
                "submitted_at": item.get("submitted_at"),
                "filled_at": item.get("filled_at"),
                "symbol": item.get("symbol"),
                "side": item.get("side"),
                "type": item.get("type"),
                "qty": item.get("qty"),
                "filled_qty": item.get("filled_qty"),
                "filled_avg_price": item.get("filled_avg_price"),
                "status": item.get("status"),
            }
        )

    exposure_pct = (market_value_total / equity) if equity else 0.0
    risk_flags = []
    if account.get("trading_blocked") or account.get("account_blocked"):
        risk_flags.append("account-blocked")
    if exposure_pct > 0.25:
        risk_flags.append("exposure-over-25pct")
    if day_pl < -500:
        risk_flags.append("daily-loss-watch")
    if unrealized_total < -500:
        risk_flags.append("open-loss-watch")

    generated_at = datetime.now(timezone.utc).isoformat()

    return {
        "mode": "paper",
        "source": "alpaca-paper-api",
        "generated_at": generated_at,
        "account": {
            "status": account.get("status"),
            "trading_blocked": account.get("trading_blocked"),
            "account_blocked": account.get("account_blocked"),
            "portfolio_value": account.get("portfolio_value") or account.get("equity"),
            "buying_power": account.get("buying_power"),
            "cash": account.get("cash"),
            "day_pl": round(day_pl, 2),
            "unrealized_pl": round(unrealized_total, 2),
            "market_value": round(market_value_total, 2),
            "exposure_pct": round(exposure_pct, 4),
        },
        "risk": {
            "flags": risk_flags,
            "open_positions": len(clean_positions),
            "max_target_exposure_pct": 0.25,
            "paper_only": True,
        },
        "clock": {
            "is_open": clock.get("is_open"),
            "timestamp": clock.get("timestamp"),
            "next_open": clock.get("next_open"),
            "next_close": clock.get("next_close"),
        },
        "runner": {
            **_runner_heartbeat(),
        },
        "portfolio_history": history,
        "positions": clean_positions,
        "orders": clean_orders,
    }


class handler(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self):
        expected = _dashboard_token()
        if not expected:
            return True
        provided = self.headers.get("X-Apex-Dashboard-Token", "")
        return provided == expected

    def do_GET(self):
        if not self._authorized():
            self._send(
                401,
                {
                    "mode": "paper",
                    "source": "alpaca-paper-api",
                    "error": "Dashboard token required.",
                    "requires_token": True,
                    "positions": [],
                    "orders": [],
                },
            )
            return
        try:
            self._send(200, _status_payload())
        except Exception as exc:
            self._send(
                503,
                {
                    "mode": "paper",
                    "source": "alpaca-paper-api",
                    "error": str(exc),
                    "positions": [],
                    "orders": [],
                },
            )
