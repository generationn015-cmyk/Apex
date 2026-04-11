# APEX Trading Bot — Setup Guide

## 1. Install Dependencies

```bash
cd trading-bot
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

For Polymarket support (optional):
```bash
pip install py-clob-client
```

---

## 2. Configure API Keys

```bash
cp .env.example .env
# Edit .env with your real API keys
nano .env
```

Also copy and customize config:
```bash
cp config.yaml config.local.yaml
# Edit config.local.yaml — set which venues/strategies to enable
nano config.local.yaml
```

---

## 3. Get API Keys

### Toobit
1. Log in to toobit.com
2. Go to Account → API Management → Create API Key
3. Enable "Trade" permissions
4. Copy API Key + Secret into `.env`

### Hyperliquid
1. Go to app.hyperliquid.xyz
2. Connect your MetaMask or hardware wallet
3. Your wallet address = `HYPERLIQUID_WALLET`
4. Export your private key from MetaMask (Settings → Security)
5. ⚠️  Use a dedicated trading wallet — never your main wallet

### Lighter.xyz
1. Go to lighter.xyz
2. Connect wallet
3. Same wallet address + private key as above (or a separate one)

### Telegram Alerts (Optional but Recommended)
1. Message @BotFather on Telegram
2. `/newbot` → follow prompts → copy the token
3. Message your new bot, then message @userinfobot for your chat_id
4. Add both to `.env`

---

## 4. Run in Paper Mode First

```bash
python main.py --paper
```

Watch signals for 1-2 days. Check:
- Are signals making sense directionally?
- What's the win rate in paper mode?
- Are stops and targets reasonable?

---

## 5. Go Live

```bash
python main.py --live
```

Or set `mode: live` in `config.local.yaml`.

---

## 6. Monitor

- Live dashboard: visible in terminal while bot runs
- Logs: `logs/apex.log`
- Database: `data/apex.db` (SQLite — open with DB Browser for SQLite)
- Telegram: get trade alerts in real time

---

## Strategy Quick Reference

| Strategy | Edge | Best Conditions | Timeframe |
|---|---|---|---|
| Momentum | Trend following with multi-TF confirmation | Trending markets, high ADX | 5m/15m/1H |
| Breakout | Volatility squeeze + volume explosion | After consolidation periods | 15m/1H |
| Funding Arb | Contrarian vs crowded trades | Extreme funding rates | 8H |
| Liq Cascade | Trade toward large liquidation clusters | High OI, volatile conditions | 5m |

---

## Risk Settings (config.yaml)

```yaml
capital:
  max_account_risk_pct: 2.0    # Never risk more than 2% per trade
  max_daily_loss_pct: 15.0     # Kill switch if down 15% in a day
  max_open_positions: 3        # Max 3 simultaneous trades
  kelly_fraction: 0.25         # Conservative Kelly sizing

leverage:
  default: 10                  # Start here — increase as you gain confidence
```

**Recommended progression:**
- Week 1: Paper mode, default settings
- Week 2: Live mode, leverage: 5, max 2 positions
- Week 3+: Gradually increase leverage as win rate proves out

---

## Troubleshooting

**"No exchanges connected"** — Check your API keys in `.env`

**"hyperliquid-python-sdk not installed"** — `pip install hyperliquid-python-sdk`

**Bot not firing signals** — Lower `min_score_to_trade` in config (try 0.40)

**Too many signals** — Raise `min_score_to_trade` (try 0.65) or disable strategies
