#!/usr/bin/env bash
set -euo pipefail
ROOT="/Users/marcuscoarchitect/.openclaw/agents/aurex/workspace/projects/context-nexus"
PYTHON="${PYTHON:-python3}"
LOG="$ROOT/release-hardening-cron.log"
mkdir -p "$ROOT"
cd "$ROOT"
{
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] cron tick start"
  "$PYTHON" "$ROOT/scripts/release_hardening_loop.py"
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] cron tick end"
} >> "$LOG" 2>&1
