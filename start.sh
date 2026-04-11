#!/bin/bash
# ============================================================
#  APEX Bot — Replit / Server Startup Script
# ============================================================
set -e

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║         APEX Trading Bot — Starting Up               ║"
echo "╚══════════════════════════════════════════════════════╝"

# Create required directories
mkdir -p logs data

# Install / update dependencies
echo "[1/2] Installing dependencies..."
pip install -q \
    "fastapi>=0.110.0" \
    "uvicorn[standard]>=0.27.0" \
    "aiohttp>=3.9.0" \
    "aiosqlite>=0.19.0" \
    "pyyaml>=6.0.1" \
    "python-dotenv>=1.0.0" \
    "httpx>=0.26.0" \
    "tenacity>=8.2.3" \
    "rich>=13.7.0" \
    "eth-account>=0.10.0" \
    "pandas>=2.1.0" \
    "numpy>=1.26.0" \
    "anthropic>=0.25.0" \
    "orjson>=3.9.10" \
    "websockets>=12.0" 2>&1 || true

# Try heavier optional deps — don't fail if unavailable
pip install -q "hyperliquid-python-sdk>=0.9.0" 2>/dev/null || \
    echo "      (hyperliquid SDK skipped — will use mock exchange)"

echo "[2/2] Starting bot in DEMO mode..."
echo ""
echo "  Dashboard will be available at the Webview tab (port 8080)"
echo "  Running with synthetic prices — no API keys needed"
echo ""

exec python main.py --demo
