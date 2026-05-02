import json
import os
import tempfile
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler


HEARTBEAT_PATH = os.path.join(tempfile.gettempdir(), "apex_runner_heartbeat.json")


def _heartbeat_token():
    return os.getenv("APEX_HEARTBEAT_TOKEN") or os.getenv("APEX_DASHBOARD_TOKEN") or os.getenv("DASHBOARD_ACCESS_TOKEN")


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
        self._send(405, {"ok": False, "error": "POST only"})
