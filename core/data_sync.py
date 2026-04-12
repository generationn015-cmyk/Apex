"""
APEX — GitHub Data Sync
Pushes live paper trading data to GitHub hourly so Streamlit Cloud
can display real results without any extra infrastructure.

Files synced:
  logs/state.json          — last cycle stats + signals
  logs/paper_trades.jsonl  — full trade ledger
  signal_engine/signals_log.jsonl  — Pocket Option signals (if exists)

Called from watchdog.py every HEARTBEAT_SECS (1h).
"""
import subprocess
import shutil
from pathlib import Path
from datetime import datetime, timezone

ROOT    = Path(__file__).parent.parent
SE_ROOT = Path.home() / "signal_engine"

# Files we track in git
TRACKED = [
    ROOT / "logs" / "state.json",
    ROOT / "logs" / "paper_trades.jsonl",
]
SE_SIGNALS = SE_ROOT / "signals_log.jsonl"


def _run(cmd: list, cwd=None) -> bool:
    try:
        result = subprocess.run(
            cmd, cwd=cwd or str(ROOT),
            capture_output=True, text=True, timeout=60,
        )
        return result.returncode == 0
    except Exception as e:
        print(f"  [DataSync] command failed: {e}")
        return False


def sync_to_github(token: str = "", remote: str = "origin") -> bool:
    """
    Commit and push live data files to GitHub.
    Call every hour from watchdog.

    token: GitHub PAT — only needed if remote URL doesn't include it.
            If empty, uses whatever credential is stored.
    """
    # Ensure logs dir exists
    (ROOT / "logs").mkdir(exist_ok=True)

    # Copy signal engine signals into apex/logs/ so they're in one repo
    if SE_SIGNALS.exists():
        dest = ROOT / "logs" / "signals_log.jsonl"
        try:
            shutil.copy2(str(SE_SIGNALS), str(dest))
            TRACKED.append(dest)
        except Exception:
            pass

    # Only stage files that actually exist
    to_add = [str(f) for f in TRACKED if f.exists()]
    if not to_add:
        print("  [DataSync] No data files to push yet")
        return False

    # Set token in remote URL if provided
    if token:
        _run(["git", "remote", "set-url", remote,
              f"https://{token}@github.com/generationn015-cmyk/Apex.git"])

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    ok = (
        _run(["git", "add"] + to_add)
        and _run(["git", "commit", "--allow-empty", "-m", f"data: live paper trading sync {stamp}"])
        and _run(["git", "push", remote, "HEAD"])
    )

    # Strip token from remote URL immediately
    if token:
        _run(["git", "remote", "set-url", remote,
              "https://github.com/generationn015-cmyk/Apex.git"])

    if ok:
        print(f"  [DataSync] Pushed live data to GitHub ({stamp})")
    else:
        print("  [DataSync] Push failed — will retry next hour")

    return ok
