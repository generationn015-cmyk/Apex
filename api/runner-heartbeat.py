import json
import os
import tempfile
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlencode
from urllib.request import Request, urlopen


HEARTBEAT_PATH = os.path.join(tempfile.gettempdir(), "apex_runner_heartbeat.json")
MAX_HISTORY = 12
PAPER_ENDPOINT = "https://paper-api.alpaca.markets"


def _heartbeat_token():
    return os.getenv("APEX_HEARTBEAT_TOKEN") or os.getenv("APEX_DASHBOARD_TOKEN") or os.getenv("DASHBOARD_ACCESS_TOKEN")


def _dashboard_token():
    return os.getenv("APEX_DASHBOARD_TOKEN") or os.getenv("DASHBOARD_ACCESS_TOKEN")


def _alpaca_headers():
    key = os.getenv("APCA_API_KEY_ID") or os.getenv("ALPACA_API_KEY")
    secret = os.getenv("APCA_API_SECRET_KEY") or os.getenv("ALPACA_API_SECRET")
    if not key or not secret:
        return None
    return {
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
        "Accept": "application/json",
    }


def _alpaca_get(path, params=None):
    headers = _alpaca_headers()
    if not headers:
        raise RuntimeError("Alpaca paper credentials are not configured.")
    query = f"?{urlencode(params)}" if params else ""
    request = Request(f"{PAPER_ENDPOINT}{path}{query}", headers=headers, method="GET")
    with urlopen(request, timeout=12) as response:
        return json.loads(response.read().decode("utf-8"))


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _fallback_heartbeat():
    try:
        account = _alpaca_get("/v2/account")
        positions = _alpaca_get("/v2/positions")
        clock = _alpaca_get("/v2/clock")
    except Exception as exc:  # noqa: BLE001 - health fallback should degrade cleanly.
        return {
            "status": "external-watchdog",
            "visible_from_vercel": False,
            "stale": True,
            "error": "heartbeat relay unavailable",
            "note": f"Waiting for local relay; Alpaca fallback unavailable: {exc.__class__.__name__}.",
        }

    symbol = "SPY"
    position = next((item for item in positions if item.get("symbol") == symbol), positions[0] if positions else {})
    qty = _safe_float(position.get("qty"))
    current_price = _safe_float(position.get("current_price"))
    equity = _safe_float(account.get("portfolio_value") or account.get("equity"))
    buying_power = _safe_float(account.get("buying_power"))
    market_value = abs(_safe_float(position.get("market_value")))
    unrealized_pl = _safe_float(position.get("unrealized_pl"))
    exposure_pct = market_value / equity if equity else 0.0
    latest_decision = "hold"
    latest_reason = "position_protected" if qty > 0 else "no_relay_no_position"
    timestamp = datetime.now(timezone.utc).isoformat()
    heartbeat = {
        "timestamp": timestamp,
        "symbol": position.get("symbol") or symbol,
        "decision": latest_decision,
        "reason": latest_reason,
        "market_open": clock.get("is_open"),
        "equity": equity,
        "buying_power": buying_power,
        "position_qty": qty,
        "latest_price": current_price,
        "dry_run": False,
        "alerts": [],
        "risk": {
            "exposure_pct": exposure_pct,
            "unrealized_pl": unrealized_pl,
            "flags": [],
            "source": "alpaca-paper-fallback",
        },
        "signals": {"actionable_count": 0, "top": []},
    }
    return _format_heartbeat([heartbeat], "alpaca-paper-fallback", "Derived from Alpaca paper account because Vercel temp relay was empty.")


def _format_heartbeat(stored, status="relay-visible", note="Best-effort Vercel relay from the local Windows watchdog."):
    heartbeat = stored[-1] if isinstance(stored, list) and stored else stored
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
        "status": status,
        "visible_from_vercel": True,
        "stale": stale,
        "age_seconds": age_seconds,
        "symbol": heartbeat.get("symbol"),
        "latest_decision": heartbeat.get("decision"),
        "latest_reason": heartbeat.get("reason"),
        "market_open": heartbeat.get("market_open"),
        "equity": heartbeat.get("equity"),
        "buying_power": heartbeat.get("buying_power"),
        "position_qty": heartbeat.get("position_qty"),
        "latest_price": heartbeat.get("latest_price"),
        "dry_run": heartbeat.get("dry_run"),
        "alerts": heartbeat.get("alerts") or [],
        "risk": heartbeat.get("risk") or {},
        "signals": heartbeat.get("signals") or {},
        "history": stored[-MAX_HISTORY:] if isinstance(stored, list) else [heartbeat],
        "last_seen": timestamp,
        "note": note,
    }


def _read_heartbeat():
    if not os.path.exists(HEARTBEAT_PATH):
        return _fallback_heartbeat()
    with open(HEARTBEAT_PATH, "r", encoding="utf-8") as f:
        stored = json.load(f)
    return _format_heartbeat(stored)


class handler(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self):
        expected = _heartbeat_token()
        if not expected:
            return False
        return self.headers.get("X-Apex-Heartbeat-Token", "") == expected

    def _dashboard_authorized(self):
        expected = _dashboard_token()
        if not expected:
            return True
        return self.headers.get("X-Apex-Dashboard-Token", "") == expected

    def do_POST(self):
        if not self._authorized():
            self._send(401, {"ok": False, "error": "heartbeat token required"})
            return
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(min(length, 8192))
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError:
            self._send(400, {"ok": False, "error": "invalid json"})
            return

        heartbeat = {
            "timestamp": payload.get("timestamp") or datetime.now(timezone.utc).isoformat(),
            "symbol": payload.get("symbol"),
            "decision": payload.get("decision"),
            "reason": payload.get("reason"),
            "market_open": payload.get("market_open"),
            "equity": payload.get("equity"),
            "buying_power": payload.get("buying_power"),
            "position_qty": payload.get("position_qty"),
            "latest_price": payload.get("latest_price"),
            "dry_run": payload.get("dry_run"),
            "alerts": payload.get("alerts") or [],
            "risk": payload.get("risk") or {},
            "signals": payload.get("signals") or {},
            "mode": "paper",
        }
        history = []
        if os.path.exists(HEARTBEAT_PATH):
            try:
                with open(HEARTBEAT_PATH, "r", encoding="utf-8") as f:
                    stored = json.load(f)
                history = stored if isinstance(stored, list) else [stored]
            except Exception:
                history = []
        incoming_history = payload.get("history")
        if isinstance(incoming_history, list):
            history.extend([item for item in incoming_history if isinstance(item, dict)])
        history.append(heartbeat)
        by_timestamp = {}
        for item in history:
            timestamp = item.get("timestamp")
            if timestamp:
                by_timestamp[timestamp] = item
        history = [by_timestamp[key] for key in sorted(by_timestamp.keys())]
        with open(HEARTBEAT_PATH, "w", encoding="utf-8") as f:
            json.dump(history[-MAX_HISTORY:], f)
        self._send(200, {"ok": True, "stored_at": datetime.now(timezone.utc).isoformat()})

    def do_GET(self):
        if not self._dashboard_authorized():
            self._send(401, {"ok": False, "error": "dashboard token required"})
            return
        try:
            self._send(200, _read_heartbeat())
        except Exception:
            self._send(
                503,
                {
                    "status": "relay-unreadable",
                    "visible_from_vercel": False,
                    "stale": True,
                    "error": "heartbeat unavailable",
                },
            )
