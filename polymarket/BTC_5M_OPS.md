# APEX 5-Min Sniper — Operations Cheatsheet

Covers **BTC and ETH** 5-minute Polymarket snipers plus the rest of the
APEX bot fleet. The watchdog is supervised by a **systemd user service**
called `apex.service` — that's what restarts it on crash, on reboot, and
when you `systemctl --user start apex`.

Every command below is **absolute-path** and copy-pasteable into any
plain bash shell on the host. You do **not** need a Claude session for
any of this.

## How the system runs

`/home/jefe/apex/watchdog.py` is supervised by `apex.service` (systemd
user unit) and itself spawns these children:

| Process            | Script                                              | Log                                            |
|--------------------|-----------------------------------------------------|------------------------------------------------|
| `apex_bot`         | `/home/jefe/apex/main.py`                           | `/home/jefe/apex/logs/apex_bot.log`            |
| `telegram_bot`     | `/home/jefe/apex/telegram/bot.py`                   | `/home/jefe/apex/logs/telegram_bot.log`        |
| `polymarket_sniper`| `/home/jefe/apex/polymarket/sniper.py`              | `/home/jefe/apex/logs/polymarket_sniper.log`   |
| `btc_5m_sniper`    | `/home/jefe/apex/polymarket/btc_5m_sniper.py`       | `/home/jefe/apex/logs/btc_5m_sniper.log`       |
| `eth_5m_sniper`    | `/home/jefe/apex/polymarket/eth_5m_sniper.py`       | `/home/jefe/apex/logs/eth_5m_sniper.log`       |
| `copy_trader`      | `/home/jefe/apex/polymarket/copy_trader.py`         | `/home/jefe/apex/logs/copy_trader.log`         |

Never launch the snipers directly in production — touch the systemd
service or kill the child PID and let the watchdog respawn it.

## Check everything is alive

```bash
systemctl --user status apex
ps -eo pid,etime,cmd | grep -E "sniper|watchdog|apex/main|telegram/bot|copy_trader" | grep -v grep
cat /home/jefe/apex/logs/watchdog_status.json
```

## Stop / start / restart everything

```bash
systemctl --user stop apex      # stops watchdog + every child
systemctl --user start apex     # starts the whole fleet from cold
systemctl --user restart apex   # bounce in one command
```

## Restart just one bot (watchdog respawns in <5s)

```bash
kill $(pgrep -f /home/jefe/apex/polymarket/btc_5m_sniper.py)
kill $(pgrep -f /home/jefe/apex/polymarket/eth_5m_sniper.py)
kill $(pgrep -f /home/jefe/apex/polymarket/sniper.py)
kill $(pgrep -f /home/jefe/apex/polymarket/copy_trader.py)
```

## Tail each bot's log

```bash
tail -f /home/jefe/apex/logs/btc_5m_sniper.log
tail -f /home/jefe/apex/logs/eth_5m_sniper.log
tail -f /home/jefe/apex/logs/polymarket_sniper.log
tail -f /home/jefe/apex/logs/copy_trader.log
tail -f /home/jefe/apex/logs/telegram_bot.log
tail -f /home/jefe/apex/logs/watchdog.log
tail -f /home/jefe/apex/logs/apex_bot.log
```

## Inspect sniper state (authoritative JSON)

```bash
/home/jefe/apex/.venv/bin/python3 -c "import json; d=json.load(open('/home/jefe/apex/polymarket/data/btc_5m_state.json')); print(json.dumps(d['stats'], indent=2)); print('bankroll:', d['bankroll'])"
/home/jefe/apex/.venv/bin/python3 -c "import json; d=json.load(open('/home/jefe/apex/polymarket/data/eth_5m_state.json')); print(json.dumps(d['stats'], indent=2)); print('bankroll:', d['bankroll'])"
```

## Go live / go paper

```bash
touch /home/jefe/apex/logs/.go_live    # enable --live on next sniper respawn
rm /home/jefe/apex/logs/.go_live       # back to paper
kill $(pgrep -f /home/jefe/apex/polymarket/btc_5m_sniper.py)
kill $(pgrep -f /home/jefe/apex/polymarket/eth_5m_sniper.py)
```

`--live` requires the `POLY_PRIVATE_KEY` already configured in
`polyconfig.py`. **Real money will move.** Only flip after a full day
of green paper WR.

## Reset a sniper's state (WIPES TRADE HISTORY)

```bash
# BTC
cp /home/jefe/apex/polymarket/data/btc_5m_state.json /home/jefe/apex/polymarket/data/btc_5m_state.backup_$(date +%s).json
/home/jefe/apex/.venv/bin/python3 -c "
import json, datetime
empty = {'bankroll': 250.0, 'trades': [], 'windows_scanned': 0,
         'windows_traded': 0, 'stats': {},
         'updated': datetime.datetime.now(datetime.timezone.utc).isoformat()}
open('/home/jefe/apex/polymarket/data/btc_5m_state.json', 'w').write(json.dumps(empty, indent=2))
"
kill $(pgrep -f /home/jefe/apex/polymarket/btc_5m_sniper.py)
```

For ETH, replace `btc_5m_state.json` with `eth_5m_state.json` and start
from `bankroll: 100.0`. **Always stop the bot first** if you want the
reset to stick — see "race conditions" below.

## Reconcile orphaned pending trades

If the hourly Telegram digest shows `Npending` that never decreases,
the sniper has trades whose 5-min windows already closed but were
missed by the live resolution loop (process restarted mid-window).
Fix:

```bash
systemctl --user stop apex                                                            # avoid race
/home/jefe/apex/.venv/bin/python3 /home/jefe/apex/polymarket/reconcile_orphan_trades.py
systemctl --user start apex
```

The script fetches Binance BTCUSDT historical klines for each closed
window, settles each orphan win/loss in place, and updates the
bankroll. Idempotent — safe to re-run.

**Race condition warning:** if you run reconcile while the sniper is
still alive, the sniper's next `save()` will overwrite your changes
with its in-memory (stale) view. Always stop the bot first.

## Debug a sniper in the foreground (detached from the watchdog)

```bash
kill $(pgrep -f /home/jefe/apex/polymarket/btc_5m_sniper.py)
/home/jefe/apex/.venv/bin/python3 /home/jefe/apex/polymarket/btc_5m_sniper.py
# Ctrl+C to exit; watchdog respawns the managed version automatically
```

## Telegram commands (same state, remote)

- `/status` — digest across every bot
- `/btc`    — BTC sniper stats
- `/stop`   — pause bots (use sparingly)
- `/live`   — toggle live mode (CAPITAL AT RISK)

## What "healthy" looks like

Every ~2s in `btc_5m_sniper.log` (or `eth_5m_sniper.log`):
```
[BTC-5M] No trade | delta=+0.012% | best_conf=50% | ticks=18
```

Every ~5min near a window close:
```
  📋 BTC-5M | DOWN | conf=70% | edge=7.2% | $20.49 | score=-8.0 | 12s left
  ✅ Resolved: DOWN | Bet: DOWN | PnL: $+1.78 | End: $72,293.01
```

### Red flags
- No "No trade" lines for >30s → sniper stuck or died
- `No start price available` repeatedly → Binance US blocked, check network
- `pending_trades` keeps growing over multiple hours → run reconcile
- Watchdog log shows a child restarting every 60s → crash loop, check that
  child's own log for the traceback

## When to worry about bankroll

```bash
grep "Resolved" /home/jefe/apex/logs/btc_5m_sniper.log | tail -50 | awk '{for(i=1;i<=NF;i++) if ($i ~ /^\$[+-]/) print $i}'
grep "Resolved" /home/jefe/apex/logs/eth_5m_sniper.log | tail -50 | awk '{for(i=1;i<=NF;i++) if ($i ~ /^\$[+-]/) print $i}'
```

A bankroll drop of >10% in a day → pause with `/stop` and investigate.

## Strategy knobs (`btc_5m_sniper.py` / `eth_5m_sniper.py`)

Located at the top of each file. **Do not change these casually.** The
BTC bot is running near 90% empirical WR and these gates are tuned to
that regime; tightening them historically would have killed more wins
than losses.

```
MIN_CONFIDENCE = 0.20     # strategy composite confidence floor
MIN_EDGE       = 0.05     # 5% edge minimum (fees eat ~3%)
MAX_BET_PCT    = 0.04     # 4% of bankroll per trade (Kelly cap)
KELLY_FRAC     = 0.25     # quarter-Kelly sizing
BTC_5M_SIGMA   = 0.003    # BTC only — 0.3% 5-min volatility
ETH_5M_SIGMA   = 0.004    # ETH only — 0.4% 5-min volatility
```

## Where things live (file paths)

```
/home/jefe/apex/                                  # repo root
  watchdog.py                                     # supervisor
  main.py                                         # apex_bot
  .env                                            # GITHUB_TOKEN, secrets
  .venv/bin/python3                               # interpreter
  logs/                                           # all bot logs + state
    .go_live                                      # presence = live mode
    watchdog.log
    btc_5m_sniper.log
    eth_5m_sniper.log
  polymarket/
    btc_5m_sniper.py                              # BTC sniper
    eth_5m_sniper.py                              # ETH sniper
    btc_strategy.py                               # SHARED strategy engine
    sniper.py                                     # general poly scanner
    copy_trader.py                                # whale mirror
    reconcile_orphan_trades.py                    # one-shot fix
    polyconfig.py                                 # bankrolls, keys
    BTC_5M_OPS.md                                 # this file
    data/
      btc_5m_state.json                           # BTC bot state
      eth_5m_state.json                           # ETH bot state
      copy_trader_state.json
      sniper_state.json
  telegram/
    bot.py                                        # /status, /btc, /live
```
