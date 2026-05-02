# Free Historical Data Sources

Date: 2026-05-02

## Shortlist

| Rank | Source / Repo | Best For | Notes |
|---|---|---|---|
| 1 | https://github.com/binance/binance-public-data | Crypto spot/futures klines, trades, aggTrades | Official, free, bulk zip files. Best free crypto backtest source. |
| 2 | Alpaca market data via `alpaca-py` | US equities/ETFs and crypto with our Alpaca keys | Best fit for Apex paper trading because execution and data come from same broker. |
| 3 | Yahoo chart endpoint / `yfinance` | Free daily equities/ETF research | Good prototype source. Unofficial, so do not treat as production-grade. |
| 4 | Stooq | Free daily equities/indices/FX | Good data, but direct CSV now may require an API key/captcha. Use only when available. |
| 5 | https://www.dukascopy-node.app/ | FX/CFD tick/minute data | Best free FX/tick source if we add Node tooling later. |

## Apex Implementation

- `scripts/backtest_spy_strategy.py`
  - Uses Stooq first.
  - Falls back to Yahoo chart data when Stooq requires an API key.
  - Backtests the same SPY strategy used by the Alpaca paper runner.

- `scripts/download_binance_klines.py`
  - Downloads official Binance Vision monthly kline zip files.
  - Saves normalized CSVs under `data/history/binance/`.

- `scripts/alpaca_status.py`
  - Shows live Alpaca paper account status without placing orders.

- `scripts/alpaca_paper_runner.py`
  - Persistent paper runner with CSV journaling to `data/paper_journal.csv`.

## Current SPY Backtest

Command:

```powershell
python scripts\backtest_spy_strategy.py --symbol SPY --start 20160101
```

Latest result:

- Source: Yahoo chart fallback
- Bars: 2597
- Period: 2016-01-04 to 2026-05-01
- Return: 36.33%
- Max drawdown: 10.0%
- Trades: 53
- Closed trades: 26
- Win rate: 46.15%
- Profit factor: 2.92

## Rule

Free data is fine for research and paper validation. Before scaling real capital, validate against broker/exchange data and include fees, spreads, slippage, and rejected fills.
