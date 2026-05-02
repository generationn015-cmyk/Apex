# Alpaca Status

## Current Finding

I did not find an Alpaca-connected paper-trading bot in the accessible trading repos or imported Apex assets.

Checked for:

- `alpaca`
- `APCA`
- `alpaca-py`
- `alpaca_trade_api`
- `paper-api.alpaca`
- `api.alpaca`

Only roadmap mentions were found in Wolf docs.

## Next Step

If Alpaca is the desired paper-trading venue, add it to Apex as a first-class exchange connector:

- `exchanges/alpaca.py`
- `.env.example` placeholders for Alpaca paper credentials
- `config.yaml` venue entry with `paper: true`
- tests for order routing in paper mode

Do not put real Alpaca keys in the repo.
