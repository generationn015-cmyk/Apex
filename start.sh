#!/bin/bash
# ============================================================
#  APEX Bot — Replit / Server Startup Script
# ============================================================

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║         APEX Trading Bot — Starting Up               ║"
echo "╚══════════════════════════════════════════════════════╝"

# Create required directories
mkdir -p logs data

# Detect Python 3 executable
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo "ERROR: Python not found in PATH!"
    exit 1
fi

echo "Python: $($PYTHON --version)"

# Install / update dependencies via the detected Python
echo "[1/2] Installing dependencies..."
$PYTHON -m pip install -q \
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
    "websockets>=12.0" 2>&1 || echo "Warning: some packages may have failed"

# Optional heavy dep — don't fail if unavailable
$PYTHON -m pip install -q "hyperliquid-python-sdk>=0.9.0" 2>/dev/null \
    && echo "hyperliquid-python-sdk: installed" \
    || echo "hyperliquid-python-sdk: skipped (will use demo prices)"

echo ""
echo "[2/2] Starting bot in DEMO mode..."
echo ""
echo "  Dashboard → open the Webview tab (port 8080)"
echo "  Synthetic prices — no API keys needed"
echo ""

exec $PYTHON main.py --demo
