# APEX — Session State (read this first)

**Purpose:** If you are a new Claude Code session opening this repo, this file is your cold-start brief. It is the source of truth for *current* live state, above stale memory or git history.

Last updated: 2026-04-15 (Opus 4.6 session — second update)

## Update — independent ETH toggle, cleaner digest, relative-path dashboard

- **Independent ETH live flag:** `logs/.go_live_eth`. BTC still uses `logs/.go_live`. Watchdog `check_live_toggle()` now watches both flags and only restarts the affected sniper.
- **New telegram commands:** `/eth_live`, `/eth_paper`. `cmd_help()` reflects them.
- **New dashboard button:** ETH pane has its own `⚡ ETH MODE CONTROL` button that opens an ETH modal with Telegram deep-links for `/eth_live`/`/eth_paper`. BTC modal is unchanged. Both modals reflect live status from `watchdog_status.json` (`processes.eth_5m_sniper.mode`).
- **Dashboard data path:** `index.html` `fetchJSON` now uses `/${path}` relative URLs so state files are served from the Vercel deployment bundle, not GitHub raw. Redeploy required for each refresh.
- **Digest cleaned up + live CLOB:** `_build_digest()` in `telegram/bot.py` shows BTC/ETH mode separately, has a divider/bar layout, and calls new `_live_clob_balance()` which hits the CLOB `get_balance_allowance(BalanceAllowanceParams(asset_type=AssetType.COLLATERAL))` for true on-chain balance.

Redeploy dashboard after any of these edits:
```
vercel deploy --prod --yes --token $(grep VERCEL_TOKEN .env | cut -d= -f2) --scope generationn015-8897s-projects
```


---

## What's running right now (live money at stake)

| Process | Path | Mode | Notes |
|---|---|---|---|
| `btc_5m_sniper.py --live` | `polymarket/btc_5m_sniper.py` | **LIVE** | Polymarket BTC 5-min up/down sniper. Real capital. |
| `eth_5m_sniper.py` | `polymarket/eth_5m_sniper.py` | paper | ETH equivalent, still in paper. |
| `telegram/bot.py` | `telegram/bot.py` | — | Handles `/live`, `/paper`, `/status`, `/pause`, `/resume` |
| `core/vercel_sync_daemon.py` | `core/vercel_sync_daemon.py` | — | Watches state files, redeploys Vercel dashboard on change (debounced 30s) |

**Watchdog (`watchdog.py`) is NOT running.** Processes are currently managed as individual nohup backgrounds. If you start the watchdog, it will spawn *new* processes on top of the existing ones — kill the existing ones first or add `logs/.disabled.<name>` flags.

## The live/paper toggle flow

1. User clicks **⚡ MODE CONTROL** button on the Vercel dashboard (`index.html`).
2. Button opens Telegram deep-link pre-filled with `/live` or `/paper`.
3. User taps Send in Telegram.
4. `telegram/bot.py` handler creates/deletes `logs/.go_live`.
5. `watchdog.py` (when running) detects flag change within its poll interval and restarts `btc_5m_sniper` with/without `--live`.
6. `btc_5m_sniper.py` only reads `--live` **at startup** — the running PID never changes mode, the watchdog owns restarts.

**Current nuance:** Because watchdog isn't running, toggling `.go_live` today does nothing automatically. Either (a) start watchdog (after killing dup children), or (b) manually restart the sniper after flipping the flag. TODO for a future session if kill-switch automation matters.

## Dashboard deployment (Vercel, no GitHub)

- **Project:** `generationn015-8897s-projects/apex-trading-hq`
- **Token:** `/root/Apex/.env` → `VERCEL_TOKEN=vcp_...` (chmod 600)
- **Deploy command:** `vercel deploy --prod --yes --token $VERCEL_TOKEN` (run from `/root/Apex`)
- **Auto-sync:** `core/vercel_sync_daemon.py` watches `polymarket/data/*_5m_state.json` + `logs/watchdog_status.json` + `logs/state.json` and redeploys on change (30s debounce).
- **GitHub is NOT used for deploys.** The old `sync_to_github.sh` and `core/data_sync.py` are dormant — ignore them unless you're restoring GitHub backup as a separate thing.

## Preflight — run before every live launch

```
python3 polymarket/preflight.py           # BTC
python3 polymarket/preflight.py --eth     # ETH
python3 polymarket/preflight.py --all     # both
```
21 checks across process integrity, CLOB API, price feeds, order book, state file, Telegram, and mode flags. Exit 0 = clear, 1 = failures.

## Known failure modes (do NOT reintroduce)

See `.claude/projects/-root/memory/feedback_sniper_bugs.md`. The ones that burned real money:
1. Duplicate `--live` instances → double orders. Lockfile in `run_sniper()`.
2. "no match" crash on thin book → must catch and retry, not propagate.
3. Unfilled FOK counted as win → always verify `size_matched > 0`.
4. Decimal precision "invalid amounts" → use `OrderArgs` with whole-share sizing, or `MarketOrderArgs`.
5. GTC orders sitting unfilled → always FOK/FAK for 5-min markets.
6. Paper/live state mixing → `.lower()` mode strings.
7. Caller ignores failed trades → `_execute_trade` returns bool.

## Recent fix (this session, 2026-04-15)

**Symptom:** Sniper firing 100%-conf signals every window but every order rejected with "Order book too thin — no asks to fill $5.00". Preflight showed $42K of ask liquidity available.

**Root cause:** `polymarket/btc_5m_sniper.py` line ~450, `limit_price = round(price, 2)`. Python's banker's rounding sent ask prices like 0.505 → 0.50, placing the FAK limit *below* the actual top ask. Every order returned "no match".

**Fix:** `limit_price = math.ceil(price * 100) / 100`. Rounds up to next cent. Our limit is always ≥ top ask → FAK matches. Edge check in `kelly_bet` already gates on `best_ask`, so ≤1¢ round-up is well inside the 3% MIN_EDGE margin — does not reintroduce the MarketOrderArgs overpay bug.

**Restart:** killed PID 41369, restarted as PID 43082 at ~17:25 UTC.

## File map

```
/root/Apex
├── polymarket/
│   ├── btc_5m_sniper.py      # LIVE — the bot
│   ├── eth_5m_sniper.py      # paper
│   ├── preflight.py          # 21-check launch gate
│   ├── polyconfig.py         # wallet + API creds
│   └── data/
│       ├── btc_5m_state.json # bankroll + trade history (source of truth)
│       └── eth_5m_state.json
├── core/
│   ├── vercel_sync_daemon.py # NEW — deploys to Vercel on state change
│   ├── live_sync_daemon.py   # old GitHub-based sync (dormant)
│   └── data_sync.py          # old GitHub sync helpers (dormant)
├── telegram/bot.py           # command handler
├── watchdog.py               # fleet manager (not running)
├── logs/
│   ├── btc_5m_sniper.log
│   ├── watchdog_status.json  # site reads this for mode/status
│   └── .go_live              # presence = LIVE mode for BTC
├── index.html                # Vercel static dashboard
├── vercel.json
└── .env                      # VERCEL_TOKEN (chmod 600)
```

## Restart recipes

**BTC sniper:**
```
kill $(cat polymarket/data/btc_5m_sniper.pid 2>/dev/null) 2>/dev/null
rm -f polymarket/data/btc_5m_sniper.pid
nohup python3 -u polymarket/btc_5m_sniper.py --live > logs/btc_5m_sniper.log 2>&1 &
disown
```

**Vercel sync daemon:**
```
nohup python3 -u core/vercel_sync_daemon.py > logs/vercel_sync.log 2>&1 &
disown
```

**Force an immediate site deploy:**
```
vercel deploy --prod --yes --token $(grep VERCEL_TOKEN .env | cut -d= -f2)
```

## Bankroll

Current: $28.40 (down from $250 starting). Reason for drawdown predates this session — read `polymarket/data/btc_5m_state.json` for trade history.
