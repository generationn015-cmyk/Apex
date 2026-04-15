#!/usr/bin/env bash
# APEX — One-shot setup for a fresh Linux/Ubuntu instance
# Run: bash setup.sh

set -e
cd "$(dirname "$0")"

echo "=== APEX Setup ==="
echo "Python: $(python3 --version)"

# Install deps
echo "Installing Python dependencies..."
pip3 install -r requirements.txt --quiet

# Create required directories
mkdir -p logs polymarket/data

# Verify CLOB connection
echo "Verifying Polymarket CLOB connection..."
python3 -c "
import sys
sys.path.insert(0, '.')
from polymarket.polyconfig import POLY_PRIVATE_KEY, CLOB_API
from py_clob_client.client import ClobClient
try:
    client = ClobClient(CLOB_API, key=POLY_PRIVATE_KEY, chain_id=137)
    client.set_api_creds(client.create_or_derive_api_creds())
    print('  CLOB: CONNECTED')
except Exception as e:
    print(f'  CLOB: {e}')
"

# Verify Telegram
echo "Verifying Telegram..."
python3 -c "
import urllib.request, urllib.parse, sys
sys.path.insert(0, '.')
from polymarket.polyconfig import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
data = urllib.parse.urlencode({'chat_id': TELEGRAM_CHAT_ID, 'text': '✅ APEX instance ready — setup complete'}).encode()
try:
    r = urllib.request.urlopen(f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage', data=data, timeout=10)
    print('  Telegram: OK')
except Exception as e:
    print(f'  Telegram: {e}')
"

echo ""
echo "=== Setup complete ==="
echo ""
echo "To start paper trading (both bots):"
echo "  bash start_paper.sh"
echo ""
echo "To start BTC live + ETH paper:"
echo "  bash start_live.sh"
