"""
APEX — Watchdog
Monitors all processes, restarts crashed ones, sends Telegram alerts.
Supports dynamic live/paper switching via logs/.go_live control file.

Usage:
    python3 watchdog.py

Processes monitored:
  - main.py                          (apex crypto bot — Lighter.xyz perps)
  - telegram/bot.py                  (telegram commands)
  - polymarket/sniper.py             (polymarket sniper)
  - ~/signal_engine/main.py          (forex signal engine — ALWAYS live, separate)
  - ~/wolf/wolf/main.py              (Wolf Polymarket/Kalshi bot)

Control files (in logs/):
  .go_live   — exists = apex_bot runs --live, absent = paper mode
  .paused    — exists = apex_bot paused (telegram /pause command)
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

LOGS_DIR    = ROOT / "logs"
LIVE_FILE   = LOGS_DIR / ".go_live"      # created by dashboard Go Live button
STATUS_FILE = LOGS_DIR / "watchdog_status.json"

_SE_ROOT   = Path.home() / "signal_engine"
_SE_UV     = _SE_ROOT / ".venv" / "bin" / "python3"
_SE_PY     = str(_SE_UV) if _SE_UV.exists() else sys.executable

_WOLF_ROOT = Path.home() / "wolf"
_WOLF_UV   = _WOLF_ROOT / ".venv" / "bin" / "python3"
_WOLF_PY   = str(_WOLF_UV) if _WOLF_UV.exists() else sys.executable

# Base process definitions (apex_bot cmd built dynamically based on LIVE_FILE)
_PROCESS_DEFS = {
    "telegram_bot": {
        "cmd": [sys.executable, str(ROOT / "telegram" / "bot.py")],
        "env_extra": {},
        "critical": True,
        "affects_live_toggle": False,
    },
    "polymarket_sniper": {
        "cmd": [sys.executable, str(ROOT / "polymarket" / "sniper.py")],
        "env_extra": {},
        "critical": False,
        "affects_live_toggle": False,
    },
    "signal_engine": {
        "cmd": [_SE_PY, str(_SE_ROOT / "main.py")],
        "env_extra": {"PYTHONPATH": str(_SE_ROOT)},
        "critical": False,
        "cwd": str(_SE_ROOT),
        "affects_live_toggle": False,  # NEVER restarted by Go Live toggle
    },
    "wolf_bot": {
        "cmd": [_WOLF_PY, str(_WOLF_ROOT / "wolf" / "main.py")],
        "env_extra": {"PYTHONPATH": str(_WOLF_ROOT)},
        "critical": False,
        "cwd": str(_WOLF_ROOT),
        "affects_live_toggle": False,
    },
}


def _apex_cmd(live: bool) -> list:
    cmd = [sys.executable, str(ROOT / "main.py")]
    if live:
        cmd.append("--live")
    return cmd


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
        self._apex_live    = LIVE_FILE.exists()   # current mode of running apex_bot
        all_names          = ["apex_bot"] + list(_PROCESS_DEFS.keys())
        self.procs: dict[str, subprocess.Popen | None] = {n: None for n in all_names}
        self.crash_count:  dict[str, int]   = {n: 0   for n in all_names}
        self.last_restart: dict[str, float] = {n: 0.0 for n in all_names}

    def _cfg(self, name: str) -> dict:
        if name == "apex_bot":
            return {
                "cmd":       _apex_cmd(self._apex_live),
                "env_extra": {},
                "critical":  True,
                "cwd":       str(ROOT),
            }
        return _PROCESS_DEFS[name]

    def start(self, name: str):
        cfg      = self._cfg(name)
        env      = {**os.environ, **cfg.get("env_extra", {})}
        log_path = LOGS_DIR / f"{name}.log"
        LOGS_DIR.mkdir(exist_ok=True)
        cwd = cfg.get("cwd", str(ROOT))
        with open(log_path, "a") as log_f:
            proc = subprocess.Popen(
                cfg["cmd"],
                stdout=log_f, stderr=subprocess.STDOUT,
                env=env, cwd=cwd,
            )
        self.procs[name]        = proc
        self.last_restart[name] = time.time()
        mode_tag = " [LIVE]" if (name == "apex_bot" and self._apex_live) else ""
        print(f"[Watchdog] Started {name}{mode_tag} (pid={proc.pid})")
        return proc

    def kill(self, name: str):
        proc = self.procs.get(name)
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
            print(f"[Watchdog] Stopped {name}")
        self.procs[name] = None

    def check_and_restart(self, name: str):
        proc = self.procs.get(name)
        if proc is None:
            self.start(name)
            return
        if proc.poll() is None:
            return
        rc = proc.returncode
        self.crash_count[name] += 1
        msg = (f"⚠️ <b>{name}</b> crashed (rc={rc}, "
               f"crash #{self.crash_count[name]}). Restarting...")
        print(f"[Watchdog] {msg}")
        _tg(msg)
        wait = min(5 * (2 ** min(self.crash_count[name] - 1, 3)), 60)
        time.sleep(wait)
        self.start(name)

    def check_live_toggle(self):
        """Detect dashboard Go Live / Go Paper toggle and restart apex_bot only."""
        want_live = LIVE_FILE.exists()
        if want_live == self._apex_live:
            return   # no change

        mode_str = "LIVE" if want_live else "PAPER"
        print(f"[Watchdog] Mode change detected → {mode_str}. Restarting apex_bot...")
        _tg(f"🔄 <b>APEX mode switching to {mode_str}</b> (dashboard toggle)")
        self.kill("apex_bot")
        self._apex_live = want_live
        time.sleep(2)
        self.start("apex_bot")
        _tg(f"{'🔴' if want_live else '📋'} <b>apex_bot restarted in {mode_str} mode</b>")

    def write_status(self):
        """Write process status to logs/watchdog_status.json for dashboard."""
        status = {}
        for name, proc in self.procs.items():
            if proc is None:
                status[name] = {"status": "not_started", "pid": None}
            elif proc.poll() is None:
                status[name] = {"status": "running",     "pid": proc.pid}
            else:
                status[name] = {"status": "dead",        "pid": None, "rc": proc.returncode}
        # Annotate apex_bot with current mode
        if "apex_bot" in status:
            status["apex_bot"]["mode"] = "live" if self._apex_live else "paper"
        # Signal engine is always independent / always live
        if "signal_engine" in status:
            status["signal_engine"]["always_live"] = True

        try:
            STATUS_FILE.write_text(json.dumps({
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "processes":  status,
            }, indent=2))
        except Exception:
            pass

    def status_line(self) -> str:
        parts = []
        for name, proc in self.procs.items():
            if proc is None:
                parts.append(f"{name}=NOT_STARTED")
            elif proc.poll() is None:
                parts.append(f"{name}=PID:{proc.pid}")
            else:
                parts.append(f"{name}=DEAD(rc={proc.returncode})")
        return " | ".join(parts)

    def stop_all(self):
        for name in list(self.procs.keys()):
            self.kill(name)


def run_watchdog():
    mgr = ProcessManager()

    # Start all processes
    for name in ["apex_bot"] + list(_PROCESS_DEFS.keys()):
        mgr.start(name)

    init_mode = "LIVE" if LIVE_FILE.exists() else "PAPER"
    _tg(f"🛡 <b>APEX Watchdog online</b>\n"
        f"Mode: {init_mode}\n"
        f"Monitoring: apex_bot, {', '.join(_PROCESS_DEFS.keys())}")

    print(f"[Watchdog] All processes started ({init_mode}). Monitoring...")

    last_heartbeat = time.time()
    CHECK_INTERVAL = 15
    HEARTBEAT_SECS = 3600

    try:
        while True:
            # Live/paper toggle check (dashboard button — never touches signal_engine)
            mgr.check_live_toggle()

            # Process health checks
            for name in ["apex_bot"] + list(_PROCESS_DEFS.keys()):
                mgr.check_and_restart(name)

            # Write status for dashboard
            mgr.write_status()

            # Hourly heartbeat
            if time.time() - last_heartbeat > HEARTBEAT_SECS:
                last_heartbeat = time.time()
                state_summary  = ""
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
