# Apex v2

A US-compliant, modular algorithmic trading system. Stocks/ETFs first via
Alpaca paper, then IBKR (futures) and regulated crypto exchanges.

**This project starts in paper-trading mode and stays there until a strategy
has demonstrated 90+ days of positive risk-adjusted returns. Do not bypass.**

## Why these strategies

Three strategies are shipped, chosen for documented edge after fees on liquid
US instruments:

- **ETF cross-sectional momentum** — 6m total return ranks across a basket of
  liquid sector / asset-class ETFs, rebalance monthly, hold equal-weighted top
  3, with a 6m absolute-momentum filter to go to cash in bear regimes.
- **RSI(2) mean reversion** — Connors-style oversold bounces on liquid US
  equities, gated to bull regimes (close > 200d SMA), ATR-based stops.
- **Donchian breakout trend follower** — turtle-style 55-day breakout / 20-day
  exit on macro ETFs, ATR-sized risk per trade. Crisis alpha.

These are not get-rich strategies. They have decades of evidence supporting
small but real positive expectancy after costs.

## Quickstart

```bash
cd apex2
pip install -r requirements.txt
cp .env.example .env   # fill in ALPACA_API_KEY/SECRET (paper)

# Backtest 5 years on each strategy
python -m apex2.runner backtest -s etf_momentum -y 5
python -m apex2.runner backtest -s rsi2_meanrev -y 5
python -m apex2.runner backtest -s donchian_trend -y 5

# Paper trade against Alpaca paper
python -m apex2.runner paper -s etf_momentum

# Live (gated)
# python -m apex2.runner live -c configs/live.yaml -s etf_momentum \
#   --i-have-validated-this-strategy-for-90-days
```

## Layout

```
apex2/
├── apex2/
│   ├── config/        # Pydantic models + YAML loader (env interpolation)
│   ├── brokers/       # Broker abstraction; Alpaca implementation
│   ├── data/          # Bar fetcher with parquet cache
│   ├── indicators/    # SMA, EMA, RSI, ATR, Donchian, momentum
│   ├── backtest/      # Event-driven engine + metrics
│   ├── risk/          # Position sizing + pre-trade gates
│   ├── strategies/    # Base class + concrete strategies + registry
│   ├── execution/     # Order routing for live/paper
│   └── runner.py      # CLI: backtest | paper | live
├── configs/           # YAML configs
└── tests/
```

## Honesty

There is no holy grail strategy. The path to profitability is:

1. Validate edge in backtest with realistic costs (already wired in).
2. Run paper trading for 90+ days. Watch for slippage/regime degradation.
3. Go live with the smallest meaningful capital. Measure for 30+ days.
4. Scale only after live results match paper within tolerance.

Skip any of these and you are gambling.
