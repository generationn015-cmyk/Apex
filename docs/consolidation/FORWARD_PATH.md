# Apex Forward Path

## Decision

Apex is the canonical trading repo.

## Architecture Target

- `main.py`, `execution/`, `risk/`, `signals/`, `strategies/`, and `exchanges/` remain the Apex core.
- Prediction-market logic from Wolf should be reviewed and promoted into Apex modules only after tests pass.
- Dashboards stay secondary. The bot must be profitable and safe before the UI gets more work.

## Priority Order

1. Confirm whether an Alpaca paper-trading bot exists and where it lives.
2. Add Alpaca as a first-class Apex exchange connector if it is missing.
3. Keep paper mode as the default.
4. Promote the best Wolf prediction-market strategy into Apex behind the Apex risk manager.
5. Keep `imports/` read-only until each module is intentionally integrated.
6. Remove duplicate imports later only after Apex has working replacements.

## Profitability Rules

- No live money until paper results prove positive expectancy after fees and slippage.
- No strategy bypasses `risk/manager.py`.
- No secrets committed.
- No autonomous live trading without explicit approval.
- Start with one strategy, one venue, tiny paper positions, and a full trade journal.

## Best Candidates

- Best core engine: Apex.
- Best prediction-market logic: Wolf.
- Best low-complexity edge to validate first: delta-neutral funding or prediction-market arbitrage.
- Avoid starting with pure AI directional calls.
