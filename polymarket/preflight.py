#!/usr/bin/env python3
"""
APEX — Trading Bot Pre-Flight Checklist
========================================
Run before going live to catch every issue that has burned us before.
Usage:
    python3 polymarket/preflight.py           # check BTC sniper
    python3 polymarket/preflight.py --eth     # check ETH sniper
    python3 polymarket/preflight.py --all     # check everything
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys, time, urllib.parse, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from polymarket.polyconfig import (
    POLY_PRIVATE_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    DATA_DIR, STARTING_BANKROLL, STARTING_BANKROLL_ETH,
)

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
WARN = "\033[93mWARN\033[0m"

results = []


def check(name: str, ok: bool, detail: str = "", warn_only: bool = False):
    tag = PASS if ok else (WARN if warn_only else FAIL)
    results.append((name, ok, warn_only))
    suffix = f" — {detail}" if detail else ""
    print(f"  [{tag}] {name}{suffix}")


def run_checks(bot: str = "btc"):
    print(f"\n{'='*60}")
    print(f"  APEX PRE-FLIGHT CHECKLIST — {bot.upper()} 5-MIN SNIPER")
    print(f"{'='*60}\n")

    script = "btc_5m_sniper.py" if bot == "btc" else "eth_5m_sniper.py"
    state_file = f"{bot}_5m_state.json"
    pid_file = f"{bot}_5m_sniper.pid"

    # ── 1. Duplicate Process Check ────────────────────────────────
    print("1. Process Integrity")
    pgrep_out = subprocess.run(
        ["pgrep", "-f", script], capture_output=True, text=True
    ).stdout.strip().split("\n")
    pids = []
    for line in pgrep_out:
        pid = line.strip()
        if not pid:
            continue
        try:
            comm = Path(f"/proc/{pid}/comm").read_text().strip()
            if "python" in comm:
                pids.append(pid)
        except (OSError, FileNotFoundError):
            continue
    check("No duplicate processes", len(pids) <= 1,
          f"{len(pids)} instances running" if len(pids) > 1 else f"{len(pids)} instance(s)")

    lock = DATA_DIR / pid_file
    if lock.exists():
        try:
            lock_pid = int(lock.read_text().strip())
            alive = Path(f"/proc/{lock_pid}").exists()
            check("PID lockfile valid", alive or len(pids) == 0,
                  f"PID {lock_pid} {'alive' if alive else 'stale'}")
        except ValueError:
            check("PID lockfile valid", False, "corrupt lockfile")
    else:
        check("PID lockfile exists", False, "no lockfile — bot not running", warn_only=True)

    # ── 2. CLOB API Connectivity ─────────────────────────────────
    print("\n2. CLOB API & Wallet")
    clob_ok = False
    try:
        from py_clob_client.client import ClobClient
        c = ClobClient("https://clob.polymarket.com", key=POLY_PRIVATE_KEY, chain_id=137)
        c.set_api_creds(c.create_or_derive_api_creds())
        clob_ok = True
        check("CLOB API connection", True)

        orders = c.get_orders()
        n = len(orders) if isinstance(orders, list) else 0
        check("No stale open orders", n == 0,
              f"{n} open orders — cancel them" if n > 0 else "0 open orders")
    except Exception as e:
        check("CLOB API connection", False, str(e))

    # ── 3. Price Feeds ───────────────────────────────────────────
    print("\n3. Price Feeds")
    for name, url, parser in [
        ("Binance US", "https://api.binance.us/api/v3/ticker/price?symbol=BTCUSDT",
         lambda d: float(d["price"])),
        ("Coinbase", "https://api.coinbase.com/v2/prices/BTC-USD/spot",
         lambda d: float(d["data"]["amount"])),
    ]:
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as f:
                price = parser(json.loads(f.read().decode()))
            check(f"{name} price feed", True, f"BTC=${price:,.2f}")
        except Exception as e:
            check(f"{name} price feed", False, str(e))

    # ── 4. Market Discovery ──────────────────────────────────────
    print("\n4. Market Discovery")
    now = int(time.time())
    window_ts = now - (now % 300)
    slug = f"btc-updown-5m-{window_ts}"
    try:
        import requests
        r = requests.get("https://gamma-api.polymarket.com/events",
                        params={"slug": slug}, timeout=10)
        events = r.json()
        found = isinstance(events, list) and len(events) > 0
        check("Gamma API event lookup", found,
              f"slug={slug}" + (" — found" if found else " — NOT FOUND"))
        if found:
            markets = events[0].get("markets", [])
            if markets:
                m = markets[0]
                prices = json.loads(m.get("outcomePrices", "[]"))
                tokens = json.loads(m.get("clobTokenIds", "[]"))
                check("Market has prices", len(prices) >= 2,
                      f"Up={prices[0]} Down={prices[1]}" if len(prices) >= 2 else "missing")
                check("Market has token IDs", len(tokens) >= 2)
    except Exception as e:
        check("Gamma API event lookup", False, str(e))

    # ── 5. Order Book Depth ──────────────────────────────────────
    print("\n5. Order Book Depth")
    if clob_ok:
        try:
            events = json.loads(urllib.request.urlopen(
                urllib.request.Request(
                    f"https://gamma-api.polymarket.com/events?slug={slug}",
                    headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
                ), timeout=10
            ).read().decode())
            if events and events[0].get("markets"):
                m = events[0]["markets"][0]
                tokens = json.loads(m.get("clobTokenIds", "[]"))
                if len(tokens) >= 2:
                    book = c.get_order_book(tokens[0])
                    asks = book.asks if hasattr(book, 'asks') else []
                    total_liq = sum(float(a.size) * float(a.price) for a in asks) if asks else 0
                    check("Order book has asks", len(asks) > 0,
                          f"{len(asks)} ask levels, ~${total_liq:.2f} liquidity")
                    check("Enough liquidity for $5 order", total_liq >= 5.0,
                          f"${total_liq:.2f} available" if total_liq >= 5 else
                          f"only ${total_liq:.2f} — 'no match' errors likely",
                          warn_only=total_liq < 5.0)
        except Exception as e:
            check("Order book check", False, str(e), warn_only=True)

    # ── 6. State File Integrity ──────────────────────────────────
    print("\n6. State File")
    state_path = DATA_DIR / state_file
    if state_path.exists():
        try:
            d = json.loads(state_path.read_text())
            bankroll = d.get("bankroll", 0)
            trades = d.get("trades", [])
            expected = STARTING_BANKROLL if bot == "btc" else STARTING_BANKROLL_ETH

            check("State file loads", True)
            check("Bankroll positive", bankroll > 0, f"${bankroll:.2f}")
            check("Bankroll reasonable", bankroll <= expected * 2,
                  f"${bankroll:.2f} vs starting ${expected:.2f}",
                  warn_only=bankroll > expected * 2)

            if trades:
                modes = set(t.get("mode", "").upper() for t in trades)
                check("No mixed paper/live trades", len(modes) <= 1,
                      f"modes found: {modes}" if len(modes) > 1 else f"all {modes.pop()}")
            else:
                check("Trade history", True, "empty — clean slate", warn_only=True)
        except json.JSONDecodeError:
            check("State file loads", False, "corrupt JSON")
    else:
        check("State file exists", False, "missing — will be created on first run", warn_only=True)

    # ── 7. Telegram ──────────────────────────────────────────────
    print("\n7. Telegram Notifications")
    check("Bot token configured", bool(TELEGRAM_BOT_TOKEN), "set" if TELEGRAM_BOT_TOKEN else "empty")
    check("Chat ID configured", bool(TELEGRAM_CHAT_ID), "set" if TELEGRAM_CHAT_ID else "empty")

    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            data = urllib.parse.urlencode({
                "chat_id": TELEGRAM_CHAT_ID,
                "text": f"[PRE-FLIGHT] {bot.upper()} 5-min sniper checklist passed",
                "parse_mode": "HTML",
            }).encode()
            urllib.request.urlopen(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                data=data, timeout=10,
            )
            check("Telegram test message", True, "sent")
        except Exception as e:
            check("Telegram test message", False, str(e))

    # ── 8. Go-Live Flag ──────────────────────────────────────────
    print("\n8. Mode Verification")
    go_live = Path("/root/Apex/logs/.go_live").exists()
    check(".go_live flag", go_live, "LIVE mode" if go_live else "PAPER mode",
          warn_only=not go_live)

    # Check actual process args
    if pids:
        for pid in pids:
            try:
                cmdline = Path(f"/proc/{pid.strip()}/cmdline").read_bytes().decode(errors="ignore")
                has_live = "--live" in cmdline
                check(f"PID {pid.strip()} has --live flag", has_live,
                      "LIVE" if has_live else "PAPER")
            except (OSError, FileNotFoundError):
                pass

    # ── Summary ──────────────────────────────────────────────────
    fails = sum(1 for _, ok, warn in results if not ok and not warn)
    warns = sum(1 for _, ok, warn in results if not ok and warn)
    passes = sum(1 for _, ok, _ in results if ok)

    print(f"\n{'='*60}")
    if fails == 0:
        print(f"  READY FOR LAUNCH: {passes} passed, {warns} warnings, {fails} failures")
    else:
        print(f"  NOT READY: {passes} passed, {warns} warnings, {fails} FAILURES")
    print(f"{'='*60}\n")

    return fails == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="APEX Trading Bot Pre-Flight Checklist")
    parser.add_argument("--eth", action="store_true", help="Check ETH sniper")
    parser.add_argument("--all", action="store_true", help="Check all bots")
    args = parser.parse_args()

    if args.all:
        btc_ok = run_checks("btc")
        results.clear()
        eth_ok = run_checks("eth")
        sys.exit(0 if btc_ok and eth_ok else 1)
    elif args.eth:
        sys.exit(0 if run_checks("eth") else 1)
    else:
        sys.exit(0 if run_checks("btc") else 1)
