#!/usr/bin/env bash
# APEX — Start BTC sniper LIVE + ETH sniper PAPER
# Requirements: VPN active on a non-US/non-EU IP (Canada, Australia, Singapore, etc.)
# Run: bash start_live.sh

cd "$(dirname "$0")"
mkdir -p logs

# Set live flag
touch logs/.go_live
echo "Live flag set: logs/.go_live"

echo "Starting BTC 5-Min Sniper (LIVE)..."
nohup python3 -u polymarket/btc_5m_sniper.py --live > logs/btc_5m_sniper.log 2>&1 &
BTC_PID=$!
echo "  BTC PID: $BTC_PID"

echo "Starting ETH 5-Min Sniper (PAPER)..."
nohup python3 -u polymarket/eth_5m_sniper.py > logs/eth_5m_sniper.log 2>&1 &
ETH_PID=$!
echo "  ETH PID: $ETH_PID"

echo ""
echo "=== LIVE MODE ACTIVE ==="
echo "BTC Sniper: LIVE  (PID $BTC_PID)"
echo "ETH Sniper: PAPER (PID $ETH_PID)"
echo ""
echo "To kill live BTC and return to paper:"
echo "  rm logs/.go_live && kill $BTC_PID"
echo ""
echo "Tail logs:"
echo "  tail -f logs/btc_5m_sniper.log"
