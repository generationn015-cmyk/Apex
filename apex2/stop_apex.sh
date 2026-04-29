#!/usr/bin/env bash
# Stop the persistent Apex v2 paper-trading wrapper.
set -euo pipefail
cd "$(dirname "$0")"

PID_FILE="logs/apex.pid"
if [[ ! -f "$PID_FILE" ]]; then
  echo "Not running (no PID file)."
  exit 0
fi

SUPERVISOR_PID=$(cat "$PID_FILE")
if ! kill -0 "$SUPERVISOR_PID" 2>/dev/null; then
  echo "Supervisor PID $SUPERVISOR_PID not found. Cleaning up."
  rm -f "$PID_FILE"
  exit 0
fi

# Kill the entire process group (supervisor + python child).
PGID=$(ps -o pgid= -p "$SUPERVISOR_PID" | tr -d ' ')
echo "Stopping Apex (PGID=$PGID)..."
kill -TERM -"$PGID" 2>/dev/null || true
sleep 2
if kill -0 "$SUPERVISOR_PID" 2>/dev/null; then
  echo "  still alive, sending KILL"
  kill -KILL -"$PGID" 2>/dev/null || true
fi

rm -f "$PID_FILE"
echo "Stopped."
