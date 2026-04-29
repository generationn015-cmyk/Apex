#!/usr/bin/env bash
# Persistent Apex v2 paper-trading wrapper.
#
# Survives shell exits. Auto-restarts on crash with exponential backoff.
# Writes a PID file so `stop_apex.sh` can shut it down cleanly.
#
# Usage:
#   ./run_apex.sh                 # paper, with default config
#   ./run_apex.sh paper.yaml      # specific config

set -euo pipefail
cd "$(dirname "$0")"

CONFIG="${1:-configs/paper.yaml}"
PID_FILE="logs/apex.pid"

mkdir -p logs data/cache

if [[ -f "$PID_FILE" ]]; then
  OLD_PID=$(cat "$PID_FILE")
  if kill -0 "$OLD_PID" 2>/dev/null; then
    echo "Already running (PID $OLD_PID). Stop with ./stop_apex.sh"
    exit 1
  fi
  rm -f "$PID_FILE"
fi

setsid nohup bash _supervisor.sh "$CONFIG" </dev/null >>logs/apex_supervisor.log 2>&1 &
APEX_PID=$!
disown $APEX_PID 2>/dev/null || true

echo "$APEX_PID" > "$PID_FILE"
sleep 2

if kill -0 "$APEX_PID" 2>/dev/null; then
  echo "Started supervisor PID $APEX_PID"
  echo "  config:  $CONFIG"
  echo "  trades:  logs/paper_launch.log"
  echo "  super:   logs/apex_supervisor.log"
  echo "  stop:    ./stop_apex.sh"
else
  echo "Failed to start. Check logs/apex_supervisor.log"
  rm -f "$PID_FILE"
  exit 1
fi
