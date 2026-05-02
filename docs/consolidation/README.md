# Trading Consolidation

Apex is the forward trading repo.

This branch imports trading-related assets from the other repos without deleting or modifying those repos. Imported code is intentionally kept under `imports/` until each piece is reviewed, tested, and promoted into the main Apex architecture.

## Imported Assets

- `imports/wolf-prediction-markets/` - Wolf prediction-market engine for Polymarket/Kalshi paper trading, risk, feeds, strategies, and dashboard backend.
- `imports/lighter-engine/` - standalone Lighter.xyz perpetual futures prototype from Wolf.
- `imports/polymarket-skill/` - Polymarket market research, watchlist, alerts, and paper portfolio tooling.
- `imports/wolf-dashboard/` - v0 Wolf dashboard UI/API project.
- `imports/uknagent-tools/` - trading signal tool stubs from UknAgent.
- `imports/uknagent-system-prompt.js` - UknAgent prompt context mentioning trading operations.

## Not Copied

- Real `.env` files, logs, PID files, SQLite databases, Python caches, `node_modules`, and `.git` folders.
- `General-Work` trading branch, because it appears to be a duplicate copy of Apex.
- Empty repos such as `T-Bots` and `Website-AI`.

## Rule Going Forward

New trading work goes in Apex first. Other repos can remain historical sources, dashboards, or experiments, but Apex should own the trading engine, risk rules, execution, and canonical docs.
