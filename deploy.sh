#!/bin/bash
# ============================================================
#  APEX Trading Bot — One-Command Server Setup
#
#  Paste this into your DigitalOcean server terminal:
#
#  bash <(curl -sL https://raw.githubusercontent.com/generationn015-cmyk/general-work/claude/automated-trading-bot-dTcjm/trading-bot/deploy.sh)
#
#  After it finishes (~5 minutes), you only need to do ONE thing:
#  Add your API keys to the .env file. That's it.
#  Claude handles all future upgrades automatically.
# ============================================================

set -e
REPO="https://github.com/generationn015-cmyk/general-work.git"
BRANCH="claude/automated-trading-bot-dTcjm"
DIR="/opt/apex-bot"
SVC="apex-bot"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║       APEX Bot — Server Setup (Auto Mode)            ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── System packages ───────────────────────────────────────────
echo "[1/7] Installing system packages..."
apt-get update -qq
apt-get install -y -qq git python3.11 python3.11-pip python3.11-venv curl ufw cron

# ── Clone repo ────────────────────────────────────────────────
echo "[2/7] Downloading bot code from GitHub..."
if [ -d "$DIR" ]; then
    cd "$DIR" && git pull -q origin "$BRANCH"
else
    git clone -q --branch "$BRANCH" "$REPO" "$DIR"
fi
cd "$DIR/trading-bot"

# ── Python environment ────────────────────────────────────────
echo "[3/7] Setting up Python environment..."
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip -q
pip install fastapi "uvicorn[standard]" aiohttp aiosqlite pyyaml \
    python-dotenv httpx tenacity rich hyperliquid-python-sdk \
    eth-account pandas numpy anthropic -q
echo "      ✓ All packages installed"

# ── Create .env ───────────────────────────────────────────────
echo "[4/7] Creating your API keys file..."
mkdir -p logs data

if [ ! -f ".env" ]; then
cat > .env << 'EOF'
# ══════════════════════════════════════════════════════════════
#  APEX Bot — API Keys
#  Fill these in, then run: systemctl restart apex-bot
# ══════════════════════════════════════════════════════════════

# ── Hyperliquid (for paper + live trading) ───────────────────
# Create a DEDICATED wallet at hyperliquid.xyz — never use your
# main wallet. Deposit USDC to start paper trading with real prices.
HYPERLIQUID_WALLET=
HYPERLIQUID_PRIVATE_KEY=

# ── Claude AI (makes trading decisions) ─────────────────────
# Get your free key at: console.anthropic.com → API Keys
# Cost: ~$0.10-0.20/day when actively trading
ANTHROPIC_API_KEY=

# ── Telegram alerts (optional) ───────────────────────────────
# Create bot: message @BotFather on Telegram
# Get your chat ID: message @userinfobot
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
EOF
    echo "      ✓ Created .env — you'll fill in keys after setup"
else
    echo "      ✓ .env already exists — keeping your keys"
fi

# ── Systemd service ───────────────────────────────────────────
echo "[5/7] Setting up auto-start service..."
cat > "/etc/systemd/system/$SVC.service" << EOF
[Unit]
Description=APEX Trading Bot
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=120
StartLimitBurst=5

[Service]
Type=simple
User=root
WorkingDirectory=$DIR/trading-bot
ExecStart=$DIR/trading-bot/venv/bin/python main.py --demo
Restart=on-failure
RestartSec=15
StandardOutput=append:$DIR/trading-bot/logs/apex.log
StandardError=append:$DIR/trading-bot/logs/apex.log
EnvironmentFile=$DIR/trading-bot/.env

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SVC" -q

# ── Auto-updater (Claude pushes upgrades via GitHub) ──────────
echo "[6/7] Setting up auto-updater (Claude can now push upgrades)..."
cp "$DIR/trading-bot/auto-update.sh" /usr/local/bin/apex-update
chmod +x /usr/local/bin/apex-update

# Run every 5 minutes
(crontab -l 2>/dev/null; echo "*/5 * * * * /usr/local/bin/apex-update") | sort -u | crontab -
echo "      ✓ Auto-updater active — Claude pushes code, server updates in <5 min"

# ── Firewall ──────────────────────────────────────────────────
echo "[7/7] Opening firewall for dashboard..."
ufw allow 22/tcp   > /dev/null 2>&1 || true
ufw allow 8080/tcp > /dev/null 2>&1 || true
ufw --force enable > /dev/null 2>&1 || true

# ── Start ─────────────────────────────────────────────────────
systemctl start "$SVC"
sleep 4

IP=$(curl -s https://ipv4.icanhazip.com 2>/dev/null || echo "YOUR_SERVER_IP")
STATUS=$(systemctl is-active "$SVC" 2>/dev/null || echo "unknown")

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║           ✓  SETUP COMPLETE                          ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║                                                      ║"
printf "║  Bot status:  %-38s║\n" "$STATUS"
printf "║  Dashboard:   http://%-32s║\n" "$IP:8080"
echo "║                                                      ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║  ONE THING LEFT TO DO:                               ║"
echo "║                                                      ║"
echo "║  Add your API keys (2 minutes):                      ║"
printf "║    nano %-44s║\n" "$DIR/trading-bot/.env"
echo "║                                                      ║"
echo "║  Then restart the bot:                               ║"
echo "║    systemctl restart apex-bot                        ║"
echo "║                                                      ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║  USEFUL COMMANDS:                                    ║"
echo "║    View logs:  tail -f /opt/apex-bot/trading-bot/logs/apex.log"
echo "║    Stop bot:   systemctl stop apex-bot               ║"
echo "║    Bot status: systemctl status apex-bot             ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "  → Open your browser now: http://$IP:8080"
echo ""
