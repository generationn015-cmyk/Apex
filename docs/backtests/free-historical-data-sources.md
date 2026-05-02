# Free Historical Data Sources

Generated: 2026-05-02

## Equity Research

| Source | Use | Setup | Notes |
|---|---|---:|---|
| Stooq CSV | Primary free daily OHLCV fallback | none | Good for long daily history; research-grade only. URL pattern: `https://stooq.com/q/d/l/?s=spy.us&d1=20160101&d2=20260502&i=d`. |
| Yahoo chart endpoint | Secondary free daily OHLCV fallback | none | Useful fallback; unofficial endpoint. URL pattern: `https://query1.finance.yahoo.com/v8/finance/chart/SPY?...&interval=1d`. |
| Alpha Vantage daily adjusted | Optional validation fallback | free key | Used only when `ALPHA_VANTAGE_API_KEY` exists locally. Uses `TIME_SERIES_DAILY_ADJUSTED` with `outputsize=full`. |

## Crypto Research

| Source | Use | Setup | Notes |
|---|---|---:|---|
| Binance Vision | Primary free crypto OHLCV bulk history | none | Official public zip files; best free source for crypto backtests. Base: `https://data.binance.vision/`. |
| Binance public REST | Gap fill / latest candles | none | Use after bulk history, not as the primary long-history loader. |

## Apex Rule

Signals are not actionable unless they pass full-history, 5Y, and 3Y gates with the same paper-runner decision logic.

## Current Scan Commands

- Equities: `python scripts\rank_equity_strategies.py --start 20160101`
- Top equity signals: `python scripts\backtest_top_signals.py --limit 25 --start 20160101 --activate-top`
- Crypto: `python scripts\backtest_binance_multi_year.py --limit 3 --start-month 2023-01`
