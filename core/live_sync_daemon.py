"""
APEX — Live Sync Daemon
Runs as a sidecar alongside watchdog.py. Watches state file mtimes; when
any change is detected (a trade fires, resolves, or the watchdog writes
status), it immediately pushes the updated data to GitHub so the Vercel
dashboard reflects reality within seconds.

Why a sidecar instead of folding this into watchdog.py: modifying the
watchdog means restarting the whole fleet, which would bounce the BTC
and ETH snipers. The user explicitly wants them to keep trading. This
daemon runs independently and can be started/stopped without touching
the snipers.

Rate limiting: pushes are debounced to once every 20 seconds max so a
burst of state writes (e.g. a trade firing → logging → resolving) only
triggers a single push.
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from core.data_sync import sync_to_github
from configs.config import GITHUB_TOKEN

LOGS_DIR   = ROOT / "logs"
POLY_DATA  = ROOT / "polymarket" / "data"

# Files to watch. When any mtime changes, fire a sync.
WATCHED = [
    POLY_DATA / "btc_5m_state.json",
    POLY_DATA / "eth_5m_state.json",
    POLY_DATA / "sniper_state.json",
    POLY_DATA / "copy_trader_state.json",
    LOGS_DIR  / "state.json",
    LOGS_DIR  / "watchdog_status.json",
]

POLL_SECS          = 5     # check mtimes every 5s
MIN_PUSH_INTERVAL  = 20    # debounce: at most one push per 20s
FALLBACK_PUSH_SECS = 600   # always push every 10 min even if nothing changed
PID_FILE           = LOGS_DIR / "live_sync_daemon.pid"
LOG_FILE           = LOGS_DIR / "live_sync_daemon.log"


def _log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    print(line, end="", flush=True)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line)
    except Exception:
        pass


def _snapshot() -> dict:
    snap = {}
    for p in WATCHED:
        try:
            snap[str(p)] = p.stat().st_mtime_ns if p.exists() else 0
        except Exception:
            snap[str(p)] = 0
    return snap


def _which_changed(old: dict, new: dict) -> list:
    return [Path(k).name for k, v in new.items() if old.get(k, 0) != v]


def _acquire_lock() -> bool:
    LOGS_DIR.mkdir(exist_ok=True)
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            import os
            os.kill(pid, 0)
            _log(f"Another live_sync_daemon is running (pid={pid}). Exiting.")
            return False
        except (ProcessLookupError, ValueError):
            pass
    import os
    PID_FILE.write_text(str(os.getpid()))
    return True


def run():
    if not _acquire_lock():
        sys.exit(1)

    if not GITHUB_TOKEN:
        _log("No GITHUB_TOKEN configured — daemon exiting (nothing to do).")
        sys.exit(0)

    _log(f"Live Sync Daemon online. Watching {len(WATCHED)} files. "
         f"Poll={POLL_SECS}s Debounce={MIN_PUSH_INTERVAL}s Fallback={FALLBACK_PUSH_SECS}s")

    last_snap  = _snapshot()
    last_push  = 0.0

    try:
        while True:
            time.sleep(POLL_SECS)
            now  = time.time()
            snap = _snapshot()
            changed = _which_changed(last_snap, snap)

            should_push = False
            reason = ""
            if changed and (now - last_push) >= MIN_PUSH_INTERVAL:
                should_push = True
                reason = f"changed: {', '.join(changed[:4])}"
            elif (now - last_push) >= FALLBACK_PUSH_SECS:
                should_push = True
                reason = "fallback heartbeat"

            if should_push:
                try:
                    ok = sync_to_github(token=GITHUB_TOKEN)
                    if ok:
                        _log(f"Pushed → {reason}")
                    else:
                        _log(f"Push skipped/failed → {reason}")
                except Exception as e:
                    _log(f"Push error ({reason}): {e}")
                last_push = now
                last_snap = snap
            elif changed:
                last_snap = snap   # update snapshot but wait for debounce
    except KeyboardInterrupt:
        _log("Shutdown (KeyboardInterrupt)")
    finally:
        try:
            PID_FILE.unlink(missing_ok=True)
        except Exception:
            pass


if __name__ == "__main__":
    run()
