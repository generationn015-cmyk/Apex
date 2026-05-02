"""Evaluate Apex paper-runner health and write local alert state."""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.alpaca_paper_runner import HEARTBEAT_HISTORY_PATH, STATE_DIR


ALERT_STATE_PATH = STATE_DIR / "apex_alert_state.json"


def load_latest_heartbeat() -> dict:
    if not HEARTBEAT_HISTORY_PATH.exists():
        return {}
    history = json.loads(HEARTBEAT_HISTORY_PATH.read_text(encoding="utf-8"))
    return history[-1] if isinstance(history, list) and history else {}


def evaluate_alerts(heartbeat: dict, max_age_seconds: int = 900) -> list[str]:
    alerts = list(heartbeat.get("alerts") or [])
    timestamp = heartbeat.get("timestamp")
    if not timestamp:
        alerts.append("missing-heartbeat")
    else:
        age = (datetime.now(UTC) - datetime.fromisoformat(timestamp.replace("Z", "+00:00"))).total_seconds()
        if age > max_age_seconds:
            alerts.append("stale-heartbeat")
    if float(heartbeat.get("equity") or 0) <= 0:
        alerts.append("equity-unavailable")
    if float(heartbeat.get("position_qty") or 0) < 0:
        alerts.append("short-position")
    return sorted(set(alerts))


def write_alert_state(alerts: list[str], heartbeat: dict) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "alerts": alerts,
        "latest_decision": heartbeat.get("decision"),
        "latest_reason": heartbeat.get("reason"),
        "symbol": heartbeat.get("symbol"),
    }
    ALERT_STATE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    heartbeat = load_latest_heartbeat()
    alerts = evaluate_alerts(heartbeat)
    write_alert_state(alerts, heartbeat)
    print("alerts:", ",".join(alerts) if alerts else "clear")
    print(ALERT_STATE_PATH)


if __name__ == "__main__":
    main()
