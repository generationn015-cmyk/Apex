# APEX 5-Min Sniper — Operations Cheatsheet

Covers BTC **and** ETH 5-minute Polymarket snipers. Everything runs under
`watchdog.py`, which supervises all bots and auto-respawns them in <5s
if a child dies.

## How the system runs

`watchdog.py` (PID in `logs/watchdog.pid`) supervises:

| Process            | Script                               | Log                             |
|--------------------|--------------------------------------|---------------------------------|
| `apex_bot`         | `main.py`                            | `logs/apex_bot.log`             |
| `telegram_bot`     | `telegram/bot.py`                    | `logs/telegram_bot.log`         |
| `polymarket_sniper`| `polymarket/sniper.py`               | `logs/polymarket_sniper.log`    |
| `btc_5m_sniper`    | `polymarket/btc_5m_sniper.py`        | `logs/btc_5m_sniper.log`        |
| `eth_5m_sniper`    | `polymarket/eth_5m_sniper.py`        | `logs/eth_5m_sniper.log`        |
| `copy_trader`      | `polymarket/copy_trader.py`          | `logs/copy_trader.log`          |

Never launch `btc_5m_sniper.py` or `eth_5m_sniper.py` directly in production —
touch the watchdog instead. If you want to debug in the foreground, kill the
managed child first (see below).

## Check everything is alive

```bash
ps -eo pid,etime,cmd | grep -E "sniper|watchdog|apex|telegram" | grep -v grep
cat logs/watchdog.pid               # supervisor PID
cat logs/watchdog_status.json       # JSON snapshot of every child
```

## Tail each bot's log

```bash
tail -f logs/btc_5m_sniper.log
tail -f logs/eth_5m_sniper.log
tail -f logs/polymarket_sniper.log
tail -f logs/copy_trader.log
tail -f logs/telegram_bot.log
tail -f logs/watchdog.log
tail -f logs/apex_bot.log
```

## Inspect sniper state (authoritative JSON)

```bash
python3 -c "import json; d=json.load(open('polymarket/data/btc_5m_state.json')); print(json.dumps(d['stats'], indent=2)); print('bankroll:', d['bankroll'])"
python3 -c "import json; d=json.load(open('polymarket/data/eth_5m_state.json')); print(json.dumps(d['stats'], indent=2)); print('bankroll:', d['bankroll'])"
```

## Restart just one sniper (watchdog respawns in <5s)

```bash
kill $(pgrep -f btc_5m_sniper.py)
kill $(pgrep -f eth_5m_sniper.py)
```

## Stop everything cleanly

```bash
kill $(cat logs/watchdog.pid)       # kills supervisor + every child
```

## Start everything cleanly

```bash
cd /home/jefe/apex
./.venv/bin/python3 watchdog.py >/dev/null 2>&1 &
echo $! > logs/watchdog.pid
```

## Go live / go paper

```bash
touch logs/.go_live                 # enables --live on next respawn
rm logs/.go_live                    # back to paper
kill $(pgrep -f btc_5m_sniper.py)   # force reload BTC sniper
kill $(pgrep -f eth_5m_sniper.py)   # force reload ETH sniper
```

**`--live` is gated on real wallet funds.** Only flip once the paper WR is
green for a full day.

## Reset sniper state (WIPES TRADE HISTORY)

```bash
cp polymarket/data/btc_5m_state.json polymarket/data/btc_5m_state.backup_$(date +%s).json
python3 -c "
import json, datetime
empty = {'bankroll': 250.0, 'trades': [], 'windows_scanned': 0,
         'windows_traded': 0, 'stats': {},
         'updated': datetime.datetime.now(datetime.timezone.utc).isoformat()}
open('polymarket/data/btc_5m_state.json', 'w').write(json.dumps(empty, indent=2))
"
kill $(pgrep -f btc_5m_sniper.py)
```

Replace paths with `eth_5m_state.json` to reset ETH.

## Reconcile orphaned pending trades

If the hourly Telegram digest shows `Npending` that never drops, run:

```bash
.venv/bin/python3 polymarket/reconcile_orphan_trades.py
```

This fetches historical Binance prices for closed windows and settles any
stuck trades in place. Idempotent — safe to re-run.

## Debug foreground run (detached from watchdog)

```bash
kill $(pgrep -f btc_5m_sniper.py)
./.venv/bin/python3 polymarket/btc_5m_sniper.py
# Ctrl+C to exit; watchdog respawns the managed version automatically
```

## Telegram commands (same state, remote)

- `/status` — digest across all bots
- `/btc`    — BTC sniper stats
- `/stop`   — pause bots (use sparingly)
- `/live`   — toggle live mode (CAPITAL AT RISK)

## What "healthy" looks like

Every ~2s in `btc_5m_sniper.log`:
```
[BTC-5M] No trade | delta=+0.012% | best_conf=50% | ticks=18
```

Every ~5min near window close:
```
  📋 BTC-5M | DOWN | conf=70% | edge=7.2% | $20.49 | score=-8.0 | 12s left
  ✅ Resolved: DOWN | Bet: DOWN | PnL: $+1.78 | End: $72,293.01
```

Same shape for `[ETH-5M]` in `eth_5m_sniper.log`.

### Red flags
- No "No trade" lines for >30s → sniper stuck or died
- "No start price available" repeatedly → Binance US blocked, check network
- `pending_trades` keeps growing over multiple hours → orphans accumulating
- Watchdog log shows a child restarting every 60s → crash loop — check
  that child's own log for the traceback

## When to worry about bankroll

```bash
# Tally recent resolutions:
grep "Resolved" logs/btc_5m_sniper.log | tail -50 | awk '{for(i=1;i<=NF;i++) if ($i ~ /^\$[+-]/) print $i}'
grep "Resolved" logs/eth_5m_sniper.log | tail -50 | awk '{for(i=1;i<=NF;i++) if ($i ~ /^\$[+-]/) print $i}'
```

Drop of >10% in a day → pause with `/stop` and investigate.

## Strategy knobs (btc_5m_sniper.py / eth_5m_sniper.py)

Located near the top of each file. **Don't change these casually** — the
BTC bot is running at a 90%+ empirical win rate and the gates are tuned
to that regime.

```
MIN_CONFIDENCE = 0.20     # strategy composite confidence floor
MIN_EDGE       = 0.05     # 5% edge minimum (fees eat ~3%)
MAX_BET_PCT    = 0.04     # 4% of bankroll per trade (Kelly cap)
KELLY_FRAC     = 0.25     # Quarter-Kelly sizing
ETH_5M_SIGMA   = 0.004    # ETH only — 0.4% 5-min volatility
BTC_5M_SIGMA   = 0.003    # BTC only — 0.3% 5-min volatility
```
