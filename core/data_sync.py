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
TD_ROOT = Path.home() / "trading-dashboard"   # copy trading + polymarket

LOGS = ROOT / "logs"

# Source → destination mappings (all land in apex/logs/ for git tracking)
POLY_DATA = ROOT / "polymarket" / "data"

SYNC_MAP = {
    # APEX crypto bot
    ROOT  / "logs" / "state.json":           LOGS / "state.json",
    ROOT  / "logs" / "paper_trades.jsonl":   LOGS / "paper_trades.jsonl",
    # Polymarket 5-min snipers + scanner (stay in polymarket/data/ in git)
    POLY_DATA / "btc_5m_state.json":         POLY_DATA / "btc_5m_state.json",
    POLY_DATA / "eth_5m_state.json":         POLY_DATA / "eth_5m_state.json",
    POLY_DATA / "sniper_state.json":         POLY_DATA / "sniper_state.json",
    POLY_DATA / "copy_trader_state.json":    POLY_DATA / "copy_trader_state.json",
    POLY_DATA / "scan_results.json":         POLY_DATA / "scan_results.json",
    # Signal engine (Pocket Option forex)
    SE_ROOT / "signals_log.jsonl":           LOGS / "signals_log.jsonl",
    # Legacy polymarket (trading-dashboard)
    TD_ROOT / "polymarket/data/open_positions.json": LOGS / "poly_open_positions.json",
    TD_ROOT / "polymarket/data/paper_results.json":  LOGS / "poly_paper_results.json",
    TD_ROOT / "polymarket/data/scan_log.jsonl":      LOGS / "poly_scan_log.jsonl",
    TD_ROOT / "polymarket/data/all_trades.jsonl":    LOGS / "poly_all_trades.jsonl",
}


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
    Commit and push live data files to GitHub every hour.
    Pulls from: APEX logs, signal_engine, trading-dashboard polymarket.
    All files land in apex/logs/ so one repo covers everything.
    """
    if not token:
        # No token configured — skip silently (set GITHUB_TOKEN env var to enable)
        return False

    LOGS.mkdir(exist_ok=True)

    # Copy all source files into apex/logs/
    staged = []
    for src, dst in SYNC_MAP.items():
        if src.exists():
            try:
                if src.resolve() != dst.resolve():
                    shutil.copy2(str(src), str(dst))
                staged.append(str(dst))
            except Exception as e:
                print(f"  [DataSync] copy {src.name} failed: {e}")
        elif dst.exists():
            staged.append(str(dst))   # keep existing file in git

    if not staged:
        print("  [DataSync] No data files to push yet")
        return False

    if token:
        _run(["git", "remote", "set-url", remote,
              f"https://{token}@github.com/generationn015-cmyk/Apex.git"])

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    ok = (
        _run(["git", "add", "-f"] + staged)
        and _run(["git", "commit", "--allow-empty", "-m", f"data: live sync {stamp}"])
        and _run(["git", "push", remote, "HEAD"])
    )

    if token:
        _run(["git", "remote", "set-url", remote,
              "https://github.com/generationn015-cmyk/Apex.git"])

    if ok:
        print(f"  [DataSync] Pushed {len(staged)} files to GitHub ({stamp})")
    else:
        print("  [DataSync] Push failed — will retry next hour")

    return ok
