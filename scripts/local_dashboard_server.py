"""Local Alpha Pack dashboard server for live paper-status preview."""

from __future__ import annotations

import importlib.util
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]


def _load_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"").strip("'"))


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_load_env()
ALPACA_STATUS = _load_module("alpaca_status", ROOT / "api" / "alpaca-status.py")
RUNNER_HEARTBEAT = _load_module("runner_heartbeat", ROOT / "api" / "runner-heartbeat.py")
RESEARCH_STATUS = _load_module("research_status", ROOT / "api" / "research-status.py")


class LocalDashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self) -> None:
        body = (ROOT / "index.html").read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path.rstrip("/")
        try:
            if path in {"", "/"}:
                self._send_html()
            elif path in {"/api/alpaca-status", "/api/alpaca-status.py"}:
                self._send_json(200, ALPACA_STATUS._status_payload())
            elif path in {"/api/runner-heartbeat", "/api/runner-heartbeat.py"}:
                self._send_json(200, RUNNER_HEARTBEAT._read_heartbeat())
            elif path in {"/api/research-status", "/api/research-status.py"}:
                self._send_json(200, RESEARCH_STATUS._payload())
            else:
                self._send_html()
        except Exception as exc:  # noqa: BLE001 - local preview should show a JSON error.
            self._send_json(503, {"ok": False, "error": str(exc), "type": exc.__class__.__name__})


def main() -> None:
    host = os.getenv("APEX_LOCAL_DASHBOARD_HOST", "127.0.0.1")
    port = int(os.getenv("APEX_LOCAL_DASHBOARD_PORT", "3000"))
    server = ThreadingHTTPServer((host, port), LocalDashboardHandler)
    print(f"Alpha Pack local dashboard ready at http://{host}:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
