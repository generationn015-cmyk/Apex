import json
import os
import tempfile
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler


HEARTBEAT_PATH = os.path.join(tempfile.gettempdir(), "apex_runner_heartbeat.json")
MAX_HISTORY = 12


def _heartbeat_token():
    return os.getenv("APEX_HEARTBEAT_TOKEN") or os.getenv("APEX_DASHBOARD_TOKEN") or os.getenv("DASHBOARD_ACCESS_TOKEN")


def _dashboard_token():
    return os.getenv("APEX_DASHBOARD_TOKEN") or os.getenv("DASHBOARD_ACCESS_TOKEN")


def _read_heartbeat():
    if not os.path.exists(HEARTBEAT_PATH):
        return {
            "status": "external-watchdog",
            "visible_from_vercel": False,
            "stale": True,
            "note": "Waiting for the local watchdog heartbeat relay.",
        }
    with open(HEARTBEAT_PATH, "r", encoding="utf-8") as f:
        stored = json.load(f)
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
        "status": "relay-visible",
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
        "note": "Best-effort Vercel relay from the local Windows watchdog.",
    }


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
