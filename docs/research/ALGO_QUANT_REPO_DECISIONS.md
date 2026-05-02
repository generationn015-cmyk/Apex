# Algo/Quant Repo Decisions

Last updated: 2026-05-02

## Use In Apex

- QuantConnect Lean: borrow modular boundaries: Data, Strategy, Risk, Execution, Broker.
- NautilusTrader: borrow event-driven discipline and backtest/live parity.
- Freqtrade: borrow dry-run-first operations, strategy optimization gates, and reporting.
- Jesse: borrow clean crypto backtest ergonomics, but do not copy execution.
- Hummingbot: borrow connector isolation and market-making risk controls only.
- vectorbt: use the idea of fast vectorized sweeps for research, then validate with Apex event-style runner.
- Backtrader/Zipline Reloaded: borrow analyzers and transaction-cost assumptions.

## Do Not Vendor Yet

- Do not import Lean, NautilusTrader, Freqtrade, Jesse, Hummingbot, vectorbt, Backtrader, or Zipline into Apex now.
- Keep Apex small until the current Alpaca paper runner has enough journaled evidence.
- Add only patterns that improve safety, tests, data integrity, and reporting.

## Immediate Application

- Keep Alpaca SPY paper runner active.
- Keep Binance crypto research read-only.
- Use the existing gate: positive return, profit factor >= 1.5, max drawdown <= 20%, at least 3 closed trades.
- Require multi-period crypto backtests before any crypto paper bot.

## Sources Checked

- https://github.com/QuantConnect/Lean
- https://github.com/nautechsystems/nautilus_trader
- https://github.com/freqtrade/freqtrade
- https://github.com/jesse-ai/jesse
- https://github.com/hummingbot/hummingbot
- https://github.com/polakowo/vectorbt
- https://github.com/mementum/backtrader
- https://github.com/stefan-jansen/zipline-reloaded
