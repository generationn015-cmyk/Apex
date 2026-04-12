"""
APEX — Watchdog
Monitors all processes, restarts crashed ones, sends Telegram alerts.

Usage:
    python3 watchdog.py

Processes monitored:
  - main.py                          (apex crypto bot — Lighter.xyz perps)
  - telegram/bot.py                  (telegram commands)
  - polymarket/sniper.py             (polymarket sniper)
  - ~/signal_engine/main.py          (forex signal engine — separate process)
  - ~/wolf/wolf/main.py              (Wolf Polymarket/Kalshi bot)
"""
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from configs.config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, STATE_FILE, TRADING_MODE

_SE_ROOT   = Path.home() / "signal_engine"
_SE_UV     = _SE_ROOT / ".venv" / "bin" / "python3"   # signal_engine has its own venv
_SE_PY     = str(_SE_UV) if _SE_UV.exists() else sys.executable

_WOLF_ROOT = Path.home() / "wolf"
_WOLF_UV   = _WOLF_ROOT / ".venv" / "bin" / "python3"  # wolf has its own venv
_WOLF_PY   = str(_WOLF_UV) if _WOLF_UV.exists() else sys.executable

PROCESSES = {
    "apex_bot": {
        "cmd": [sys.executable, str(ROOT / "main.py")],
        "env_extra": {},
        "critical": True,
    },
    "telegram_bot": {
        "cmd": [sys.executable, str(ROOT / "telegram" / "bot.py")],
        "env_extra": {},
        "critical": True,
    },
    "polymarket_sniper": {
        "cmd": [sys.executable, str(ROOT / "polymarket" / "sniper.py")],
        "env_extra": {},
        "critical": False,
    },
    "signal_engine": {
        "cmd": [_SE_PY, str(_SE_ROOT / "main.py")],
        "env_extra": {"PYTHONPATH": str(_SE_ROOT)},
        "critical": False,  # Forex signals — informational, not blocking live trading
        "cwd": str(_SE_ROOT),
    },
    "wolf_bot": {
        "cmd": [_WOLF_PY, str(_WOLF_ROOT / "wolf" / "main.py")],
        "env_extra": {"PYTHONPATH": str(_WOLF_ROOT)},
        "critical": False,  # Polymarket / Kalshi — runs independently
        "cwd": str(_WOLF_ROOT),
    },
}

# Add --live flag if TRADING_MODE is live
if TRADING_MODE == "live":
    PROCESSES["apex_bot"]["cmd"].append("--live")


def _tg(text: str):
    data = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
    }).encode()
    try:
        urllib.request.urlopen(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data=data, timeout=10
        )
    except Exception:
        pass


class ProcessManager:
    def __init__(self):
        self.procs: dict[str, subprocess.Popen | None] = {
            name: None for name in PROCESSES
        }
        self.crash_count: dict[str, int] = {name: 0 for name in PROCESSES}
        self.last_restart: dict[str, float] = {name: 0.0 for name in PROCESSES}

    def start(self, name: str):
        cfg = PROCESSES[name]
        env = {**os.environ, **cfg.get("env_extra", {})}
        log_path = ROOT / "logs" / f"{name}.log"
        log_path.parent.mkdir(exist_ok=True)

        cwd = cfg.get("cwd", str(ROOT))
        with open(log_path, "a") as log_f:
            proc = subprocess.Popen(
                cfg["cmd"],
                stdout=log_f,
                stderr=subprocess.STDOUT,
                env=env,
                cwd=cwd,
            )
        self.procs[name] = proc
        self.last_restart[name] = time.time()
        print(f"[Watchdog] Started {name} (pid={proc.pid})")
        return proc

    def check_and_restart(self, name: str):
        proc = self.procs.get(name)
        cfg  = PROCESSES[name]

        # Not started yet
        if proc is None:
            self.start(name)
            return

        # Still running
        if proc.poll() is None:
            return

        # Dead — restart
        rc = proc.returncode
        self.crash_count[name] += 1
        msg = (f"⚠️ <b>{name}</b> crashed (rc={rc}, "
               f"crash #{self.crash_count[name]}). Restarting...")
        print(f"[Watchdog] {msg}")
        _tg(msg)

        # Exponential backoff: 5s, 10s, 20s … max 60s
        wait = min(5 * (2 ** min(self.crash_count[name] - 1, 3)), 60)
        time.sleep(wait)
        self.start(name)

    def status_line(self) -> str:
        parts = []
        for name, proc in self.procs.items():
            if proc is None:
                parts.append(f"{name}=NOT_STARTED")
            elif proc.poll() is None:
                parts.append(f"{name}=PID:{proc.pid}")
            else:
                parts.append(f"{name}=DEAD(rc={proc.poll()})")
        return " | ".join(parts)

    def stop_all(self):
        for name, proc in self.procs.items():
            if proc and proc.poll() is None:
                proc.terminate()
                print(f"[Watchdog] Stopped {name}")


def run_watchdog():
    mgr = ProcessManager()

    # Start everything
    for name in PROCESSES:
        mgr.start(name)

    _tg(f"🛡 <b>APEX Watchdog online</b>\n"
        f"Mode: {TRADING_MODE.upper()}\n"
        f"Monitoring: {', '.join(PROCESSES.keys())}")

    print("[Watchdog] All processes started. Monitoring...")

    last_heartbeat = time.time()
    CHECK_INTERVAL = 15    # Check every 15 seconds
    HEARTBEAT_SECS = 3600  # Telegram heartbeat every hour

    try:
        while True:
            # Check each process
            for name in PROCESSES:
                mgr.check_and_restart(name)

            # Hourly heartbeat
            if time.time() - last_heartbeat > HEARTBEAT_SECS:
                last_heartbeat = time.time()
                state_summary = ""
                try:
                    if STATE_FILE.exists():
                        state = json.loads(STATE_FILE.read_text())
                        stats = state.get("stats", {})
                        state_summary = (
                            f"\nPnL: ${stats.get('total_pnl', 0):.2f}  |  "
                            f"WR: {stats.get('win_rate', 0)}%"
                        )
                except Exception:
                    pass
                _tg(f"💓 <b>Watchdog heartbeat</b>{state_summary}\n"
                    f"{mgr.status_line()}")

            time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        print("\n[Watchdog] Shutting down...")
        mgr.stop_all()
        _tg("🛑 APEX Watchdog stopped (KeyboardInterrupt)")


if __name__ == "__main__":
    run_watchdog()
