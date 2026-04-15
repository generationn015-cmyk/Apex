#!/usr/bin/env bash
# APEX — Start both snipers in PAPER mode
# Run: bash start_paper.sh

cd "$(dirname "$0")"
mkdir -p logs

echo "Starting BTC 5-Min Sniper (PAPER)..."
nohup python3 -u polymarket/btc_5m_sniper.py > logs/btc_5m_sniper.log 2>&1 &
echo "  BTC PID: $!"

echo "Starting ETH 5-Min Sniper (PAPER)..."
nohup python3 -u polymarket/eth_5m_sniper.py > logs/eth_5m_sniper.log 2>&1 &
echo "  ETH PID: $!"

echo ""
echo "Both snipers running in PAPER mode."
echo "Logs: tail -f logs/btc_5m_sniper.log"
echo "       tail -f logs/eth_5m_sniper.log"
