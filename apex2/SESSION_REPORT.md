# Apex v2 — Session Status Report

## Live state (paper)

- **Account:** PA346MOE9XFO (Alpaca paper, $100k start)
- **Equity:** $100,020.29 (+$20.29, +0.02%)
- **Cash:** $90,744.79
- **Open position:** SPY × 13 @ $711.94 (Donchian, trend_entry — first session, +0.22%)
- **Process:** supervisor PID 8814 (orphaned to init, will outlive session)
- **Strategies live:** RSI(2) mean reversion + Donchian 55/20 trend
- **Polling:** 60s when market open; 5-min sleep when closed
- **Auto-restart:** exponential backoff up to 10 min on crash
- **Stop with:** `cd apex2 && ./stop_apex.sh`

## What I built this session

### Three new strategies (all disqualified — gates worked)

| Strategy | Sharpe | MDD | Verdict |
|---|---|---|---|
| pairs_trading | -0.43 | -7.15% | ❌ Loses money (PF 0.91) |
| bond_equity_rotation | 0.03 | -11.7% | ❌ Too slow (only 2 trades in 5y) |
| defensive_momentum | 0.62 | -2.8% | ❌ Below 0.7 Sharpe gate (but PF 3.48) |

This is a feature, not a failure: 3 of 6 strategies tested cleared the bar.
Most quant ideas don't beat costs. Strict gates protect the portfolio.

### Validation infrastructure

- **Walk-forward optimization** (`backtest/walkforward.py`) — Optuna-based parameter search with rolling IS/OOS windows. Catches overfit by reporting IS-vs-OOS Sharpe decay.
- **Monte Carlo trade resampling** (`backtest/monte_carlo.py`) — bootstraps the trade-return series 3,000x, returns p05/p50/p95 of final return and max drawdown. Shows realistic dispersion.
- **VIX regime filter** (`risk/vix_filter.py`) — protection guard that blocks new entries when VIX ≥ 25. Cached 1h. Tunes via `threshold` param.
- **FRED data source** (`data/fred.py`) — free macro data (yield curve, VIX history, unemployment, CPI). No auth required.

### TradingAgents-light (Claude-powered overlay)

Read the [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) framework: 5 LLM agents (Analyst/Researcher/Trader/Risk/PM) in structured debate. For our daily-bar bot the full thing is overkill (8+ API calls × $0.05+ per signal). I extracted the three highest-leverage patterns:

`apex2/agents/advisor.py`:

1. **`daily_briefing()`** — Claude classifies regime as risk_on/neutral/risk_off once per day. Cached. Cost: ~$0.001/day with prompt caching on Haiku 4.5.
2. **`pre_trade_veto()`** — Optional pre-order check ("any obvious reason to block this BUY in the next session — earnings/halt/M&A?"). Daily call budget caps cost. Defaults to ALLOW on any error or missing API key.
3. **`trade_journal()`** — Structured JSONL log of every submit + veto + outcome. Ready for weekly retrospective prompts.

**All three are opt-in.** Without `ANTHROPIC_API_KEY`, the bot runs identically to before. Set `use_advisor=True` in the runner to activate, plus add `ANTHROPIC_API_KEY` to `.env`.

### Persistence (`run_apex.sh` + `_supervisor.sh` + `stop_apex.sh`)

- `setsid nohup` detaches the supervisor from the spawning shell — survives session/SSH/Claude exits
- Supervisor loop calls the runner; on crash, restarts with exponential backoff (10s → 600s cap)
- PID file at `logs/apex.pid`; clean shutdown via `./stop_apex.sh`
- Two log streams: `apex_supervisor.log` (lifecycle events) and `paper_launch.log` (trade activity)

## What I need from you

In rough priority:

### 1. Anthropic API key (optional, but unlocks the LLM overlay)

Add to `apex2/.env`:
```
ANTHROPIC_API_KEY=sk-ant-...
APEX_VETO_DAILY_LIMIT=50      # cost cap; raise/lower per taste
APEX_ADVISOR_MODEL=claude-haiku-4-5
```
Then in the next session I'll wire `use_advisor=True` into the paper runner. Estimated cost: ~$0.10–$0.50/day at current trade volumes.

### 2. Decide on going live

The recommendation hasn't changed:
- **Strategy:** RSI(2) only first 14 days, then add Donchian
- **Cap:** $500 hard ceiling first 30 days
- **Daily-loss kill:** -3% (already wired)
- **Single open position** at a time
- **Live config:** copy `configs/live.yaml.example` → `configs/live.yaml`, fill keys
- **Launch:** `python -m apex2.runner live -c configs/live.yaml -s rsi2_meanrev --i-have-validated-this-strategy-for-90-days`

The flag name is intentionally aggressive. Think before typing it.

### 3. Optional add-ons I can build next session

- **Web dashboard** (FastAPI on port 8080) showing equity curve, open positions, recent fills
- **Telegram alerts** on every fill / risk rejection / daily PnL summary (you have the infrastructure ready in `monitoring/`)
- **Weekly Claude retrospective** that reads `data/trade_journal.jsonl` and generates a "what worked / what didn't" memo
- **More strategies that might actually work**: PEAD (post-earnings drift, needs paid earnings calendar API), short-volatility ETF carry (SVXY/VXX), low-vol factor with hedge

### 4. Things I will NOT do without explicit instruction

- Submit any LIVE order with real money (stays gated behind the long flag)
- Increase risk parameters above the live config defaults (0.5% per trade, 1 position, $500 cap)
- Disable any protection guard
- Trade options or futures (Phase 2 only after IBKR is wired and a strategy has live track record)
- Touch crypto until Coinbase Advanced is configured

## Repo state

- Branch: `claude/bot-profitability-analysis-CGJ8r`
- Tests: 21/21 passing
- Total apex2 size: ~3,000 LOC across 28 files
- Last commit before this report: a9ee589 (this report adds ~2k more lines on top)

## How to check on it without me

```bash
cd /home/user/Apex/apex2

# Is it alive?
cat logs/apex.pid && ps -p $(cat logs/apex.pid)

# Recent trade activity
tail -20 logs/paper_launch.log

# Account status (uses .env)
python -c "
import os; from dotenv import load_dotenv; load_dotenv()
from alpaca.trading.client import TradingClient
c = TradingClient(api_key=os.environ['ALPACA_API_KEY'],
                  secret_key=os.environ['ALPACA_API_SECRET'], paper=True)
acct = c.get_account()
print(f'Equity \${float(acct.equity):,.2f}  Cash \${float(acct.cash):,.2f}')
for p in c.get_all_positions():
    print(f'  {p.symbol}: {p.qty}@\${float(p.avg_entry_price):.2f}  uPL=\${float(p.unrealized_pl):.2f}')
"

# Stop
./stop_apex.sh

# Restart
./run_apex.sh configs/paper.yaml
```
