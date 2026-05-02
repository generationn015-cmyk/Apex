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
NOTIFICATION_PATH = STATE_DIR / "apex_notifications.json"
NOTIFICATION_LOG_PATH = ROOT / "logs" / "apex_notifications.log"


def load_latest_heartbeat() -> dict:
    if not HEARTBEAT_HISTORY_PATH.exists():
        return {}
    history = json.loads(HEARTBEAT_HISTORY_PATH.read_text(encoding="utf-8"))
    return history[-1] if isinstance(history, list) and history else {}


def evaluate_alerts(heartbeat: dict, max_age_seconds: int = 900) -> list[str]:
    alerts = list(heartbeat.get("alerts") or [])
    alerts.extend((heartbeat.get("risk") or {}).get("flags") or [])
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


def build_notifications(alerts: list[str], heartbeat: dict) -> list[dict]:
    generated_at = datetime.now(UTC).isoformat()
    notifications: list[dict] = []
    for alert in alerts:
        notifications.append(
            {
                "generated_at": generated_at,
                "level": "warning",
                "title": alert,
                "symbol": heartbeat.get("symbol"),
                "decision": heartbeat.get("decision"),
                "reason": heartbeat.get("reason"),
            }
        )
    signals = (heartbeat.get("signals") or {}).get("top") or []
    for signal in signals:
        if signal.get("actionable"):
            notifications.append(
                {
                    "generated_at": generated_at,
                    "level": "signal",
                    "title": "actionable-paper-signal",
                    "symbol": signal.get("symbol"),
                    "decision": signal.get("decision"),
                    "reason": signal.get("reason"),
                    "score": signal.get("score"),
                }
            )
    return notifications


def write_alert_state(alerts: list[str], heartbeat: dict) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    notifications = build_notifications(alerts, heartbeat)
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "alerts": alerts,
        "notifications": notifications,
        "latest_decision": heartbeat.get("decision"),
        "latest_reason": heartbeat.get("reason"),
        "symbol": heartbeat.get("symbol"),
    }
    ALERT_STATE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    NOTIFICATION_PATH.write_text(json.dumps(notifications, indent=2), encoding="utf-8")
    if notifications:
        NOTIFICATION_LOG_PATH.parent.mkdir(exist_ok=True)
        with NOTIFICATION_LOG_PATH.open("a", encoding="utf-8") as f:
            for item in notifications:
                f.write(json.dumps(item, sort_keys=True) + "\n")


def main() -> None:
    heartbeat = load_latest_heartbeat()
    alerts = evaluate_alerts(heartbeat)
    write_alert_state(alerts, heartbeat)
    print("alerts:", ",".join(alerts) if alerts else "clear")
    print("notifications:", len(build_notifications(alerts, heartbeat)))
    print(ALERT_STATE_PATH)


if __name__ == "__main__":
    main()
