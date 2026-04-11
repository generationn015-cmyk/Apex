#!/usr/bin/env python3
"""
APEX Trading Bot — Laptop Installer
====================================
Give this single file to your agent or run it yourself.
Works on Mac, Windows, and Linux.

Usage:
    python install.py

What it does (fully automated):
    1. Checks Python version (needs 3.10+)
    2. Clones the bot code from GitHub
    3. Creates an isolated Python environment
    4. Installs all dependencies
    5. Creates your API keys file (.env)
    6. Creates required folders
    7. Starts the bot in demo mode
    8. Opens the dashboard in your browser
"""

import os
import sys
import subprocess
import platform
import shutil
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
REPO_URL    = "https://github.com/generationn015-cmyk/general-work.git"
BRANCH      = "claude/automated-trading-bot-dTcjm"
INSTALL_DIR = Path.home() / "apex-bot"
BOT_DIR     = INSTALL_DIR / "trading-bot"
PYTHON      = sys.executable

PACKAGES = [
    "fastapi",
    "uvicorn[standard]",
    "aiohttp",
    "aiosqlite",
    "pyyaml",
    "python-dotenv",
    "httpx",
    "tenacity",
    "rich",
    "hyperliquid-python-sdk",
    "eth-account",
    "pandas",
    "numpy",
    "anthropic",
    "ccxt",
    "python-telegram-bot",
    "web3",
    "websockets",
    "orjson",
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def banner(text):
    print(f"\n{'='*55}")
    print(f"  {text}")
    print(f"{'='*55}")

def step(n, text):
    print(f"\n[{n}] {text}...")

def ok(text):
    print(f"    ✓  {text}")

def fail(text):
    print(f"    ✗  {text}")
    sys.exit(1)

def run(cmd, cwd=None, capture=False):
    result = subprocess.run(
        cmd, shell=True, cwd=cwd,
        capture_output=capture, text=True
    )
    return result

# ── Steps ─────────────────────────────────────────────────────────────────────

def check_python():
    step(1, "Checking Python version")
    v = sys.version_info
    if v < (3, 10):
        fail(f"Python 3.10+ required. You have {v.major}.{v.minor}. "
             f"Download from https://python.org")
    ok(f"Python {v.major}.{v.minor}.{v.micro}")

def check_git():
    step(2, "Checking Git")
    if shutil.which("git") is None:
        fail("Git not found. Install from https://git-scm.com/downloads then re-run this script.")
    ok("Git found")

def clone_repo():
    step(3, "Downloading APEX bot from GitHub")
    if INSTALL_DIR.exists():
        print(f"    Directory {INSTALL_DIR} already exists — pulling latest updates...")
        r = run(f'git -C "{INSTALL_DIR}" pull origin {BRANCH}', capture=True)
        if r.returncode != 0:
            print(f"    Pull failed — re-cloning fresh...")
            shutil.rmtree(INSTALL_DIR)
            r = run(f'git clone --branch {BRANCH} {REPO_URL} "{INSTALL_DIR}"', capture=True)
            if r.returncode != 0:
                fail(f"Clone failed: {r.stderr}")
    else:
        r = run(f'git clone --branch {BRANCH} {REPO_URL} "{INSTALL_DIR}"', capture=True)
        if r.returncode != 0:
            fail(f"Clone failed: {r.stderr}\n\nMake sure you have internet access.")
    ok(f"Code downloaded to {INSTALL_DIR}")

def create_venv():
    step(4, "Creating Python virtual environment")
    venv_dir = INSTALL_DIR / "venv"
    if not venv_dir.exists():
        r = run(f'"{PYTHON}" -m venv "{venv_dir}"', capture=True)
        if r.returncode != 0:
            fail(f"venv creation failed: {r.stderr}")
    ok(f"Virtual environment ready at {venv_dir}")
    return venv_dir

def get_venv_python(venv_dir):
    if platform.system() == "Windows":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"

def install_packages(venv_dir):
    step(5, "Installing dependencies (this takes 2-3 minutes)")
    venv_python = get_venv_python(venv_dir)
    pkg_list = " ".join(f'"{p}"' for p in PACKAGES)
    r = run(f'"{venv_python}" -m pip install --upgrade pip -q', capture=True)
    r = run(f'"{venv_python}" -m pip install {pkg_list} -q')
    if r.returncode != 0:
        # Try without -q for better error visibility
        run(f'"{venv_python}" -m pip install {pkg_list}')
    ok("All packages installed")

def create_env_file():
    step(6, "Creating API keys file")
    env_path = BOT_DIR / ".env"
    if env_path.exists():
        ok(".env already exists — keeping your existing keys")
        return

    env_path.write_text("""\
# ══════════════════════════════════════════════════════════════
#  APEX Bot — API Keys
#  Fill these in when you're ready to trade with real prices.
#  The bot runs in demo mode without any keys.
# ══════════════════════════════════════════════════════════════

# ── Hyperliquid (needed for paper + live trading) ────────────
# Create a DEDICATED wallet at hyperliquid.xyz
# NEVER put your main wallet's private key here
HYPERLIQUID_WALLET=
HYPERLIQUID_PRIVATE_KEY=

# ── Claude AI (makes the trading decisions) ──────────────────
# Get a free API key at: console.anthropic.com → API Keys
# Cost: ~$0.10-0.20 per day when the bot is actively trading
ANTHROPIC_API_KEY=

# ── Telegram alerts (optional — trade notifications) ─────────
# Create a Telegram bot: message @BotFather
# Get your chat ID: message @userinfobot
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
""")
    ok(f".env created at {env_path}")
    print(f"\n    → IMPORTANT: Open this file and add your keys when ready:")
    print(f"      {env_path}")

def create_folders():
    step(7, "Creating log and data folders")
    (BOT_DIR / "logs").mkdir(exist_ok=True)
    (BOT_DIR / "data").mkdir(exist_ok=True)
    ok("Folders created")

def start_bot(venv_dir):
    step(8, "Starting APEX bot in demo mode")
    venv_python = get_venv_python(venv_dir)

    print("\n" + "="*55)
    print("  APEX BOT STARTING")
    print("="*55)
    print("\n  Dashboard: http://localhost:8080")
    print("  Open that URL in your browser now.")
    print("\n  The bot is running in DEMO MODE —")
    print("  synthetic prices, no real money, no API keys needed.")
    print("\n  To stop:  press Ctrl+C")
    print("="*55 + "\n")

    # Try to open browser
    try:
        import webbrowser, threading, time
        def open_browser():
            time.sleep(4)
            webbrowser.open("http://localhost:8080")
        threading.Thread(target=open_browser, daemon=True).start()
    except Exception:
        pass

    # Run the bot (blocks until Ctrl+C)
    os.chdir(BOT_DIR)
    os.execv(str(venv_python), [str(venv_python), "main.py", "--demo"])

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    banner("APEX Trading Bot — Laptop Setup")
    print(f"\n  Installing to: {INSTALL_DIR}")
    print(f"  Platform: {platform.system()} {platform.machine()}")

    check_python()
    check_git()
    clone_repo()
    venv = create_venv()
    install_packages(venv)
    create_env_file()
    create_folders()

    banner("Setup Complete ✓")
    print(f"""
  Bot installed at:  {INSTALL_DIR}
  API keys file:     {BOT_DIR / '.env'}
  Logs:              {BOT_DIR / 'logs' / 'apex.log'}

  NEXT TIME you want to run the bot:
    cd {BOT_DIR}
    {get_venv_python(venv)} main.py --demo

  To trade with REAL prices (after adding Hyperliquid keys):
    {get_venv_python(venv)} main.py --paper

  To go LIVE (after paper trading successfully):
    {get_venv_python(venv)} main.py --live
""")

    start_now = input("  Start the bot now? [Y/n]: ").strip().lower()
    if start_now in ("", "y", "yes"):
        start_bot(venv)
    else:
        print("\n  Run later with:")
        print(f"    cd {BOT_DIR}")
        print(f"    {get_venv_python(venv)} main.py --demo")
        print()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Setup cancelled.")
