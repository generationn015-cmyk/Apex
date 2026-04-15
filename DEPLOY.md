# APEX — Deploy on Fresh Instance

## Prerequisites
- Python 3.10 or 3.11
- VPN active on a **non-US / non-EU** IP (Canada, Australia, Singapore, Japan, Mexico all work)
- Git

## Quick Start

```bash
git clone https://github.com/generationn015-cmyk/Apex.git
cd Apex
bash setup.sh
```

## Run Paper Mode (both bots)
```bash
bash start_paper.sh
```

## Run Live Mode (BTC live, ETH paper)
```bash
bash start_live.sh
```

## Monitor
```bash
tail -f logs/btc_5m_sniper.log
tail -f logs/eth_5m_sniper.log
```

## Kill Switch (return BTC to paper)
```bash
rm logs/.go_live
kill $(pgrep -f btc_5m_sniper)
```

## Key Files
- `polymarket/btc_5m_sniper.py` — BTC 5-min sniper engine
- `polymarket/eth_5m_sniper.py` — ETH 5-min sniper engine  
- `polymarket/btc_strategy.py` — 7-indicator MACD strategy
- `polymarket/polyconfig.py` — wallet key + Telegram config
- `logs/.go_live` — exists = BTC runs live; absent = paper
