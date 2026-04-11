#!/bin/bash
# ============================================================
#  APEX Bot — Auto-Updater
#  Runs every 5 minutes via cron.
#  Checks GitHub for new commits — if found, pulls and restarts.
#  This is how Claude pushes upgrades to your server automatically.
# ============================================================

REPO_DIR="/opt/apex-bot"
BRANCH="claude/automated-trading-bot-dTcjm"
SERVICE="apex-bot"
LOG="/opt/apex-bot/trading-bot/logs/auto-update.log"

cd "$REPO_DIR" || exit 1

# Fetch latest without changing working tree
git fetch origin "$BRANCH" --quiet 2>&1

LOCAL=$(git rev-parse HEAD 2>/dev/null)
REMOTE=$(git rev-parse "origin/$BRANCH" 2>/dev/null)

if [ "$LOCAL" = "$REMOTE" ]; then
    exit 0   # Nothing to do
fi

echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] UPDATE DETECTED" >> "$LOG"
echo "  Old: $LOCAL" >> "$LOG"
echo "  New: $REMOTE" >> "$LOG"

# Pull the update
git pull origin "$BRANCH" --quiet 2>&1 >> "$LOG"

# Install any new Python dependencies
cd "$REPO_DIR/trading-bot"
source venv/bin/activate
pip install -r requirements.txt -q >> "$LOG" 2>&1

# Restart the bot service
systemctl restart "$SERVICE"
echo "  Bot restarted successfully" >> "$LOG"
echo "" >> "$LOG"
