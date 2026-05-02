import json
import os
import tempfile
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler


HEARTBEAT_PATH = os.path.join(tempfile.gettempdir(), "apex_runner_heartbeat.json")


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
            "mode": "paper",
        }
        with open(HEARTBEAT_PATH, "w", encoding="utf-8") as f:
            json.dump(heartbeat, f)
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
