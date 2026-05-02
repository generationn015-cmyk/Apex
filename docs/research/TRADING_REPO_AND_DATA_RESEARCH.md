# Trading Repo and Data Research

Date: 2026-05-02

## Decision

Apex remains our canonical repo. We should not replace Apex with another bot. We should selectively borrow architecture ideas and integrate official data/broker SDKs.

## Best Trading Bot / Engine Repos

| Repo | Use For | Verdict |
|---|---|---|
| https://github.com/freqtrade/freqtrade | Crypto strategy lifecycle: dry-run, data download, backtesting, hyperopt, strategy analysis | Best reference for retail crypto bot workflow. Do not copy code blindly because it is GPL-3.0. |
| https://github.com/hummingbot/hummingbot | Market making, exchange connectors, CEX/DEX connector patterns | Best reference for market-making and connector design. |
| https://github.com/Drakkar-Software/OctoBot | User-friendly crypto automation, visual UI, DCA/grid/TradingView/AI strategy workflows | Good UX/reference repo. Use as product/design reference, not core engine. |
| https://github.com/jesse-ai/jesse | Crypto strategy research and backtesting with strong anti-lookahead emphasis | Good strategy/backtesting workflow reference. |
| https://github.com/nautechsystems/nautilus_trader | Production-grade event-driven backtesting/live architecture | Best long-term architecture reference. Heavy, but very strong. |
| https://github.com/QuantConnect/Lean | Institutional multi-asset backtesting/live trading engine | Best reference for research rigor and brokerage/data abstraction. Too heavy to embed now. |
| https://github.com/nkaz001/hftbacktest | Order book, queue position, latency-aware HFT backtesting | Best if we later do market making or high-frequency crypto/perps. |
| https://github.com/Polymarket/py-clob-client | Official Polymarket CLOB Python client | Use directly for prediction-market execution/data. |
| https://github.com/wangzhe3224/awesome-systematic-trading | Curated systematic trading resource list | Use for discovery and library comparisons. |
| https://github.com/botcrypto-io/awesome-crypto-trading-bots | Curated crypto bot/resource list | Use for discovery only. |

## Best Historical Data Repos / SDKs

| Repo / SDK | Markets | Use For | Verdict |
|---|---|---|---|
| https://github.com/alpacahq/alpaca-py | US stocks, crypto, options | Alpaca paper trading, account/orders, historical bars/news | First integration target because user wants Alpaca paper. |
| https://github.com/databento/databento-python | Futures, equities, options, OPRA, market-by-order/order book datasets | Professional historical tick/order-book data | Best serious backtest data source once budget allows. |
| https://github.com/binance/binance-public-data | Crypto spot and futures | Free historical klines/trades/aggTrades | Best free crypto history source. |
| https://github.com/massive-com/client-python | Stocks, options, forex, crypto | Historical/live market data via Polygon/Massive | Good paid/general market data provider. |
| https://github.com/Leo4815162342/dukascopy-node | FX, CFDs, crypto, commodities, ETFs | Free tick/minute/hourly/daily data | Best free FX/CFD historical source. |
| https://github.com/ranaroussi/yfinance | Stocks/ETFs | Cheap prototype data | Use only for early research, not production trading. |

## Apex Build Plan

### Phase 1: Paper Trading Backbone

1. Add `exchanges/alpaca.py` using `alpaca-py`.
2. Add `data_sources/alpaca.py` for historical stock/crypto bars.
3. Add `data_sources/binance_public.py` for crypto historical data downloads.
4. Add a normalized internal candle/trade schema so every source outputs the same format.
5. Add a local storage layer, preferably Parquet under `data/history/`, ignored by git.

### Phase 2: Backtesting Gate

1. Backtest every strategy before paper trading.
2. Include fees, slippage, spread, and rejected fills.
3. Require walk-forward validation.
4. Require out-of-sample results before paper deployment.
5. Track expectancy, max drawdown, Sharpe, win rate, profit factor, and average trade.

### Phase 3: Strategy Candidates

Start with these, in order:

1. Delta-neutral / funding carry for crypto/perps.
2. Prediction-market arbitrage / mispricing from Wolf.
3. Simple equities momentum/mean reversion on Alpaca paper.
4. Market making only after we have order-book data and latency-aware backtests.

Avoid starting with:

- Pure LLM directional predictions.
- High leverage.
- Unvalidated scalping.
- Cross-venue execution before the data and risk layer are stable.

## Integration Rules

- Apex owns execution, risk, config, logging, and canonical strategy interfaces.
- External repos are references or dependencies, not random pasted code.
- All live/paper broker calls must go through Apex exchange connectors.
- All strategies must go through `risk/manager.py`.
- No real credentials in the repo.
- Paper mode is default.

## Immediate Next Implementation

Build the Alpaca paper connector first:

- `exchanges/alpaca.py`
- `data_sources/alpaca.py`
- `tests/test_alpaca_config.py`
- `tests/test_alpaca_paper_connector.py`
- `.env.example` placeholder keys only
- `config.yaml` venue entry with `paper: true`

Then add historical data ingestion:

- `data_sources/binance_public.py`
- `data_sources/schema.py`
- `data_sources/storage.py`
- `data/history/.gitkeep`

## Sources

- Freqtrade: https://github.com/freqtrade/freqtrade
- Hummingbot: https://github.com/hummingbot/hummingbot
- OctoBot: https://github.com/Drakkar-Software/OctoBot
- Jesse: https://github.com/jesse-ai/jesse
- NautilusTrader: https://github.com/nautechsystems/nautilus_trader
- QuantConnect LEAN: https://github.com/QuantConnect/Lean
- Awesome Systematic Trading: https://github.com/wangzhe3224/awesome-systematic-trading
- Awesome Crypto Trading Bots: https://github.com/botcrypto-io/awesome-crypto-trading-bots
- Databento Python: https://github.com/databento/databento-python
- Binance public data: https://github.com/binance/binance-public-data
- Alpaca Python SDK: https://github.com/alpacahq/alpaca-py
- Polymarket clients: https://docs.polymarket.com/developers/CLOB/clients
- Dukascopy Node: https://www.dukascopy-node.app/
