# Apex v2 — 5-Year Backtest Results

**Test period:** April 2021 → April 2026 (~5 years)
**Initial capital:** $10,000
**Data source:** yfinance daily bars
**Slippage:** 2 bps adverse on every fill
**Commissions:** $0 (Alpaca commission-free for stocks/ETFs)
**Fill model:** next bar open (no look-ahead, signal at close → fill at next open)

## Strategy Results

| Strategy | CAGR | Sharpe | Sortino | Max DD | Win Rate | Trades | Profit Factor |
|---|---|---|---|---|---|---|---|
| ETF momentum (12-1) | 5.55% | 0.45 | 0.51 | -22.66% | 53.6% | 69 | 1.56 |
| RSI(2) mean reversion | **7.57%** | **1.09** | **1.05** | **-8.09%** | 74.8% | 258 | 1.96 |
| Donchian 55/20 trend | **10.12%** | **1.10** | **1.31** | **-8.67%** | 50.8% | 61 | 2.25 |
| **Portfolio (RSI2 + Donchian)** | **8.01%** | **1.33** | **1.65** | **-6.31%** | 67.3% | 284 | 2.04 |

## Verdicts

- **ETF momentum**: ❌ Disqualified. Sharpe 0.45 is below the 0.5 floor; max drawdown of -22.7% is unacceptable. The 12-month rebalance cadence on a 13-ETF universe couldn't overcome 2021–2022 regime shifts.
- **RSI(2) mean reversion**: ✓ Deploy candidate. High win rate (75%), tight drawdown, clean Sharpe.
- **Donchian trend**: ✓ Deploy candidate. Lower hit rate (51%) but biggest avg win (2.16%/trade) and best CAGR.
- **Portfolio (RSI2 + Donchian)**: ✓ **Recommended live deployment.** Combining the two pushes Sharpe to 1.33, drawdown to -6.3%, and 36 winning months vs 22 losing.

## Why the portfolio improves on either alone

The two strategies trade structurally opposite premises:

- **RSI(2)** profits when oversold reversions follow noise (works in chop, ranges)
- **Donchian** profits when persistent trends emerge (works in directional regimes)

Their P&L curves are negatively correlated by design. When mean reversion is failing (2022 trend year), trend follower is winning. When trend is failing (chop), reversion mops up.

## Monthly stats (portfolio)

- Best month: +5.11%
- Worst month: -2.34%
- Average month: +0.65%
- Winning months: 36 / 58 (62%)
- Longest drawdown: 410 bars (~ 19 months underwater equity-wise; recovered)

## Live deployment plan

The portfolio config is the recommended live deployment. With $500 starting capital:

- $250 allocated to RSI(2) — short-term oversold bounces on liquid ETFs
- $250 allocated to Donchian — 55-day breakout / 20-day exit
- Daily-loss kill at -3% (portfolio level)
- Max 1 open position per strategy initially
- 30-day live trial; scale up only after live tracks paper within ±25%

## Caveats

1. **Yahoo Finance data**: dividends adjusted, split-adjusted; minor discrepancies vs Alpaca live data possible.
2. **No survivorship bias**: ETF universe is pre-selected and existed throughout the period (clean).
3. **No regime filter beyond strategy-internal**: a structural break in 2026+ could degrade results. The protection chain (max-DD halt, max-consecutive-losses, cooldown) is the safety net.
4. **5 years is the minimum credible window**. Longer would be better. Adding 2008-2009 to the test would test crisis behavior; planned for Phase 2.
5. **Per-trade returns are small** (RSI2: 0.6% avg). The strategy depends on cumulative edge over many trades — a few bad months don't invalidate it.

## Reproduce

```bash
cd apex2
python -m apex2.runner backtest -c configs/backtest.yaml -s rsi2_meanrev -y 5
python -m apex2.runner backtest -c configs/backtest.yaml -s donchian_trend -y 5
python -m apex2.runner portfolio -c configs/backtest.yaml --strategies "rsi2_meanrev,donchian_trend" -y 5
```
