#!/bin/bash
# Unattended driver for the whole context-plugins trial: plugin smoke tests (step 6), then the
# pilot/batch/H chain (steps 7-10). Resumable end to end: a smoke run or batch with output is skipped.
#   setsid nohup trial/run-context-plugins-all.sh > ~/agent-trials/context-plugins.log 2>&1 < /dev/null &
set -u
KIT=$(cd "$(dirname "$0")" && pwd)
DATA=${TRIAL_DATA:-$HOME/agent-trials}
export TRIAL_DATA QWEN_METRICS_URL=${QWEN_METRICS_URL:-http://192.168.50.232:8001/metrics}
log() { echo "$(date '+%F %T') $*"; }

# Step 6 smoke tests: one short run each on t2 (V4 as a capped H run). Skipped per-run if graded.
if [ ! -f "$DATA/smoke/.done" ]; then
  log ">>> smoke tests"
  export BATCH=smoke
  for v in V1 V2 V3 V5 V6; do
    [ -f "$DATA/smoke/logs/opencode-$v-t2-1.grade.json" ] && { log "skip smoke $v"; continue; }
    VARIANT=$v bash "$KIT/run_trial.sh" opencode t2 1
    log "smoke $v rc=$?"
  done
  [ -f "$DATA/smoke/logs/opencode-V4-t2-1.grade.json" ] || {
    VARIANT=V4 SCENARIO=H H_STEPS=10 bash "$KIT/run_trial.sh" opencode t2 1
    log "smoke V4-H rc=$?"
  }
  "$DATA/venv/bin/python" "$KIT/smoke_check.py" > "$DATA/smoke/EVIDENCE.md" 2>&1
  log "smoke evidence: $DATA/smoke/EVIDENCE.md"
  touch "$DATA/smoke/.done"
fi

exec "$KIT/run-context-plugins.sh"
