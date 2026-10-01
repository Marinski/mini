#!/bin/bash
# Run the whole context-plugins trial unattended (SPEC-context-plugins.md steps 6-10).
#
#   setsid nohup trial/run-context-plugins.sh > ~/agent-trials/context-plugins.log 2>&1 < /dev/null &
#
# It is resumable: every batch is skipped once its REPORT.md exists, and every run inside a batch is
# skipped once it has a grade, so re-running continues where it stopped. The window gate is on
# (nights only, backup windows clear); set WINDOW_GATE=0 to run at any hour. Smoke tests (step 6)
# are run by hand before this, because their proofs need a human read of the request bodies.
set -u
KIT=$(cd "$(dirname "$0")" && pwd)
DATA=${TRIAL_DATA:-$HOME/agent-trials}
export QWEN_METRICS_URL=${QWEN_METRICS_URL:-http://192.168.50.232:8001/metrics}
export WINDOW_GATE=${WINDOW_GATE:-1}
TASKS=${TASKS:-"t2 t8 t9"}
# Per-task longest pilot run (minutes); the gate pads by WINDOW_PAD. Update after the pilot.
export TASK_LONGEST=${TASK_LONGEST:-"t2:25 t8:35 t9:70"}
log() { echo "$(date '+%F %T') $*"; }

run_batch() {  # run_batch <batch> <variants> <reps> <tasks> [SCENARIO]
  local batch=$1 variants=$2 reps=$3 tasks=$4 scenario=${5:-single}
  [ -f "$DATA/$batch/REPORT.md" ] && { log "skip $batch (REPORT.md exists)"; return 0; }
  mkdir -p "$DATA/$batch"
  log ">>> $batch variants=[$variants] reps=$reps tasks=[$tasks] scenario=$scenario"
  ( cd "$KIT" && BATCH=$batch VARIANTS="$variants" SCENARIO="$scenario" ./queue.sh opencode "$reps" "$tasks" ) \
    >> "$DATA/$batch/batch.log" 2>&1
  local rc=$?
  [ "$rc" = 3 ] && { log "!! $batch halted: Qwen froze"; exit 3; }
  log "<<< $batch done (rc=$rc)"
}

log "=== context-plugins chain start (pid $$) gate=$WINDOW_GATE ==="

# 7. Pilot: one rep of every variant on all three tasks; drop the clear losers.
run_batch ctx-pilot "V0 V1 V2 V3 V4 V5 V6" 1 "$TASKS"
SURV=$("$DATA/venv/bin/python" "$KIT/select.py" --pilot "$DATA/ctx-pilot" 2>>"$DATA/context-plugins.log")
[ -z "$SURV" ] && { log "pilot left no surviving variants; stopping"; exit 0; }
log "pilot survivors: $SURV"
# V4 was the pilot-only control; it is not in scenario S beyond the pilot.
SURV=$(echo "$SURV" | grep -v '^V4$' | tr '\n' ' ')

# 8. Full batch, staged. Stage A: 3 reps for V0 and survivors.
run_batch ctx-a "V0 $SURV" 3 "$TASKS"
FINAL=$("$DATA/venv/bin/python" "$KIT/select.py" --finalists "$DATA/ctx-a" 2>>"$DATA/context-plugins.log")
log "Stage A finalists: ${FINAL:-none}"
if [ -n "$FINAL" ]; then
  run_batch ctx-b "V0 $FINAL" 3 "$TASKS"
fi

# 9. Scenario H on t9 for the variants still in the trial (V4 only reaches S as the pilot control).
H_VAR="V0"
for v in V3 V4 V6; do
  case " $SURV " in *" $v "*) H_VAR="$H_VAR $v" ;; esac
done
run_batch ctx-h "$H_VAR" 3 "t9" "H"

# 10. Report: the S decision from Stage A + Stage B merged, then H, in one file.
mkdir -p "$KIT/../results"
STAGES="ctx-a"; [ -n "$FINAL" ] && STAGES="ctx-a ctx-b"
BATCH=ctx-final "$DATA/venv/bin/python" "$KIT/summarize.py" --batches "$STAGES" \
  --out "$KIT/../results/context-plugins.md" > /dev/null 2>>"$DATA/context-plugins.log"
if [ -f "$DATA/ctx-h/REPORT.md" ]; then
  { echo; echo "---"; echo; echo "# Scenario H (handover), per session"; echo;
    sed -n '/## Scenario H/,$p' "$DATA/ctx-h/REPORT.md"; } >> "$KIT/../results/context-plugins.md"
fi
log "=== chain complete; report: $KIT/../results/context-plugins.md ==="
