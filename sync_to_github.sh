#!/bin/bash
# APEX — Auto-sync state files to GitHub for Vercel dashboard
# Runs via cron every 2 minutes
cd /root/Apex || exit 1

# Only push if state files changed
CHANGED=$(git diff --name-only -- polymarket/data/ logs/watchdog_status.json 2>/dev/null)
if [ -z "$CHANGED" ]; then
    exit 0
fi

git add polymarket/data/btc_5m_state.json \
        polymarket/data/eth_5m_state.json \
        logs/watchdog_status.json 2>/dev/null

git commit -m "data: live state sync $(date -u +%H:%M)" --no-gpg-sign -q 2>/dev/null || exit 0
git push origin master -q 2>/dev/null
