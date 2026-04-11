#!/usr/bin/env python3
"""
APEX Bot — First-Run Setup Script
Checks environment, installs deps, validates config, runs preflight checks.
"""
import os
import sys
import subprocess

def check_python():
    if sys.version_info < (3, 10):
        print("❌  Python 3.10+ required. You have:", sys.version)
        sys.exit(1)
    print(f"✅  Python {sys.version_info.major}.{sys.version_info.minor}")

def install_deps():
    print("\n📦  Installing dependencies...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "-q"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print("❌  pip install failed:")
        print(result.stderr)
        sys.exit(1)
    print("✅  Dependencies installed")

def check_env():
    print("\n🔑  Checking API keys (.env file)...")
    if not os.path.exists(".env"):
        print("⚠️   No .env file found — copying template...")
        import shutil
        shutil.copy(".env.example", ".env")
        print("📄  Created .env — open it and fill in your keys:\n")
        print("    Required for Hyperliquid (primary venue):")
        print("    HYPERLIQUID_WALLET=0x...     ← your EVM wallet address")
        print("    HYPERLIQUID_PRIVATE_KEY=0x... ← private key (use a DEDICATED wallet!)")
        print("\n    Optional (for Telegram alerts):")
        print("    TELEGRAM_BOT_TOKEN=...")
        print("    TELEGRAM_CHAT_ID=...")
        return False

    from dotenv import load_dotenv
    load_dotenv()

    issues = []
    if not os.getenv("HYPERLIQUID_WALLET"):
        issues.append("HYPERLIQUID_WALLET not set")
    if not os.getenv("HYPERLIQUID_PRIVATE_KEY"):
        issues.append("HYPERLIQUID_PRIVATE_KEY not set")

    if issues:
        print("⚠️   Missing keys in .env:")
        for issue in issues:
            print(f"    - {issue}")
        print("\n    Edit .env and re-run this script.")
        return False

    print("✅  API keys found")
    return True

def check_config():
    print("\n⚙️   Checking config...")
    config_file = "config.local.yaml" if os.path.exists("config.local.yaml") else "config.yaml"
    import yaml
    with open(config_file) as f:
        config = yaml.safe_load(f)

    mode = config.get("bot", {}).get("mode", "paper")
    balance = config.get("capital", {}).get("starting_balance_usd", 0)
    lev = config.get("leverage", {}).get("default", 10)

    print(f"    Config file:     {config_file}")
    print(f"    Trading mode:    {mode.upper()}")
    print(f"    Starting capital: ${balance}")
    print(f"    Default leverage: {lev}x")

    if mode == "live":
        print("\n⚠️   LIVE MODE — real money will be traded!")
        ans = input("    Type 'YES' to confirm: ")
        if ans != "YES":
            print("    Aborted.")
            sys.exit(0)
    else:
        print("✅  Paper mode (safe to run)")

def make_dirs():
    os.makedirs("logs", exist_ok=True)
    os.makedirs("data", exist_ok=True)

def main():
    print("=" * 55)
    print("  APEX Trading Bot — Setup & Preflight Check")
    print("=" * 55)

    check_python()
    install_deps()
    keys_ok = check_env()
    if keys_ok:
        check_config()
    make_dirs()

    print("\n" + "=" * 55)
    if keys_ok:
        print("  ✅  All checks passed — ready to launch!")
        print()
        print("  Paper mode (recommended first):  python main.py --paper")
        print("  Live mode (when ready):          python main.py --live")
        print("  Aggressive mode:                 python main.py --config config.aggressive.yaml --live")
        print()
        print("  Dashboard will appear in terminal.")
        print("  Logs: logs/apex.log  |  DB: data/apex.db")
    else:
        print("  ⚠️   Complete setup above, then re-run: python setup.py")
    print("=" * 55)

if __name__ == "__main__":
    main()
