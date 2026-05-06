from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
BRIEF_PATH = ROOT / "runtime" / "evolution" / "automation_brief.md"
BACKLOG_PATH = ROOT / "runtime" / "evolution" / "improvement_backlog.md"
HEARTBEAT_PATH = ROOT / "runtime" / "alpaca_paper_runner.heartbeat"
LOG_PATH = ROOT / "logs" / "telegram_morning_update.log"


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def tail_text(path: Path, max_chars: int = 1400) -> str:
    if not path.exists():
        return "No file found yet."
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if len(text) <= max_chars:
        return text
    return text[-max_chars:].lstrip()


def heartbeat_status() -> str:
    if not HEARTBEAT_PATH.exists():
        return "No runner heartbeat found."
    line = HEARTBEAT_PATH.read_text(encoding="utf-8", errors="replace").splitlines()[-1]
    try:
        ts_raw = line.split(" ", 1)[0]
        ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        age_min = (datetime.now(timezone.utc) - ts.astimezone(timezone.utc)).total_seconds() / 60
        return f"Heartbeat age: {age_min:.1f} min"
    except Exception:
        return f"Heartbeat present: {line[:120]}"


def build_message() -> str:
    brief = tail_text(BRIEF_PATH, 1200)
    backlog = tail_text(BACKLOG_PATH, 700)
    return (
        "Alpha Pack Morning Check\n"
        f"{datetime.now().strftime('%Y-%m-%d %H:%M %Z')}\n\n"
        f"{heartbeat_status()}\n\n"
        "Latest automation brief:\n"
        f"{brief}\n\n"
        "Current evolution backlog:\n"
        f"{backlog}"
    )[:3900]


def send_telegram(token: str, chat_id: str, message: str) -> None:
    payload = urlencode(
        {
            "chat_id": chat_id,
            "text": message,
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    request = Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        method="POST",
    )
    with urlopen(request, timeout=20) as response:
        body = response.read().decode("utf-8", errors="replace")
        result = json.loads(body)
    if not result.get("ok"):
        raise RuntimeError(f"Telegram rejected message: {body[:500]}")


def log(message: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(f"{datetime.now(timezone.utc).isoformat()} {message}\n")


def main() -> int:
    load_env_file(ENV_PATH)
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        log("telegram skipped: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing")
        print("Telegram morning update is configured but missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID.")
        return 2
    try:
        send_telegram(token, chat_id, build_message())
    except (HTTPError, URLError, TimeoutError, RuntimeError) as exc:
        log(f"telegram failed: {exc}")
        print(f"Telegram morning update failed: {exc}")
        return 1
    log("telegram sent")
    print("Telegram morning update sent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
