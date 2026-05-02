# Apex Repo Cleanup Map

Canonical path:

- `scripts/alpaca_paper_runner.py` - paper runner
- `api/` - Vercel dashboard APIs
- `index.html` - live dashboard
- `scripts/backtest_*.py` and `scripts/rank_equity_strategies.py` - research gates
- `docs/backtests/` - generated research reports
- `runtime/`, `logs/`, `data/paper_journal.csv` - ignored local state

Do not use for production trading:

- `imports/` - retained reference imports only
- legacy exchange adapters not wired to Alpaca paper mode
- crypto strategy research until passing backtest gate

Cleanup rule:

- Archive by documentation first.
- Do not delete imported repo folders until the strategy/report they contain has been summarized.
- Do not enable live trading without explicit approval.
