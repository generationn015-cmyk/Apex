#!/usr/bin/env bash
# Internal supervisor loop. Spawned detached by run_apex.sh; do not invoke directly.
# $1 = config file relative to apex2/
set -uo pipefail

cd "$(dirname "$0")"

CONFIG="${1:-configs/paper.yaml}"
LOG_FILE="logs/apex_supervisor.log"
TASK_LOG="logs/paper_launch.log"

mkdir -p logs data/cache

backoff=10
echo "[$(date -Iseconds)] supervisor PID=$$ started config=$CONFIG" >> "$LOG_FILE"

while true; do
  echo "[$(date -Iseconds)] starting paper loop" >> "$LOG_FILE"
  python -m apex2.runner paper -c "$CONFIG" --poll 60 >> "$TASK_LOG" 2>&1
  rc=$?
  echo "[$(date -Iseconds)] paper loop exited rc=$rc; backoff=${backoff}s" >> "$LOG_FILE"
  if [[ $rc -eq 0 ]]; then
    backoff=10
  fi
  sleep "$backoff"
  backoff=$(( backoff * 2 ))
  if [[ $backoff -gt 600 ]]; then backoff=600; fi
done
