import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEARSHEET_DIR = ROOT / "docs" / "backtests" / "tearsheets"
CACHE_REPORT = ROOT / "docs" / "backtests" / "cache-metadata-report.md"
WALK_FORWARD = ROOT / "docs" / "backtests" / "walk-forward-report.md"


def _dashboard_token():
    return os.getenv("APEX_DASHBOARD_TOKEN") or os.getenv("DASHBOARD_ACCESS_TOKEN")


def _file_summary(path: Path) -> dict:
    if not path.exists():
        return {"exists": False}
    return {
        "exists": True,
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "updated_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
        "bytes": path.stat().st_size,
    }


def _tearsheets() -> list[dict]:
    if not TEARSHEET_DIR.exists():
        return []
    rows = []
    for path in sorted(TEARSHEET_DIR.glob("*-tearsheet.md")):
        rows.append(
            {
                "symbol": path.name.split("-")[0].upper(),
                **_file_summary(path),
            }
        )
    return rows


def _payload() -> dict:
    tearsheets = _tearsheets()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tearsheet_count": len(tearsheets),
        "tearsheets": tearsheets[:12],
        "cache_metadata": _file_summary(CACHE_REPORT),
        "walk_forward": _file_summary(WALK_FORWARD),
        "mode": "research-only",
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
        expected = _dashboard_token()
        if not expected:
            return True
        return self.headers.get("X-Apex-Dashboard-Token", "") == expected

    def do_GET(self):
        if not self._authorized():
            self._send(401, {"ok": False, "error": "dashboard token required"})
            return
        self._send(200, _payload())
