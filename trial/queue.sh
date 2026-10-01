#!/bin/bash
# Run a field x tasks x reps one at a time on Qwen, then build the report and post it to Discord.
# Usage: BATCH=batch6 queue.sh "<harness ...>" [reps] [tasks]
#        BATCH=ctx VARIANTS="V0 V1 V2 V3 V5 V6" queue.sh opencode [reps] [tasks]
# Start it with nohup/setsid and append to $TRIAL_DATA/$BATCH/batch.log.
#
# Field: a space list of harnesses, or (with VARIANTS set) of OpenCode variants. The field is
# iterated fastest, then tasks, then reps, so consecutive runs never share a variant/time block
# (SPEC step 7's round-robin).
# Resume: a run whose grade already exists is skipped, so re-running continues the batch.
# Window: WINDOW_GATE=1 starts a run only if it fits the night window and the backup windows are
# left clear (SPEC step 8); a run waits for the next opening otherwise. Default off, so the
# harness batches keep running whenever they are asked to.
set -u
KIT=$(cd "$(dirname "$0")" && pwd)
DATA=${TRIAL_DATA:-$HOME/agent-trials}
export BATCH=${BATCH:-batch6}
HARNESSES=$1; REPS=${2:-3}; TASKLIST=${3:-"t1 t2 t6"}
VARIANTS=${VARIANTS:-}
SCENARIO=${SCENARIO:-single}
# Per-task longest pilot run (minutes), for the window gate. The gate pads it (WINDOW_PAD).
TASK_LONGEST=${TASK_LONGEST:-"t2:20 t8:35 t9:65"}
# Variant runs are the trial's, so the nights-only gate defaults on for them; harness batches keep
# the historical behaviour (any hour) unless WINDOW_GATE=1 is asked for.
WINDOW_GATE=${WINDOW_GATE:-$([ -n "$VARIANTS" ] && echo 1 || echo 0)}
B=$DATA/$BATCH; mkdir -p "$B"

longest() {  # longest <task> -> minutes
  for e in $TASK_LONGEST; do [ "${e%%:*}" = "$1" ] && { echo "${e##*:}"; return; }; done
  echo 45
}

# Never share Qwen (or a key) with another trial run: wait for any running one to end.
# Anchored to a bash process running a trial script, so a shell that merely mentions the path does
# not count; the running queue excludes itself by pid.
wait_others() {
  while pgrep -f '(^|[/. ])(run_trial|queue)\.sh( |$)' | grep -vx "$$" >/dev/null; do sleep 30; done
}

gate() {  # gate <task>: block until a run of that task fits the open window
  [ "$WINDOW_GATE" = 1 ] || return 0
  local min s
  min=$(longest "$1")
  # An H run is two sessions on the same task, so it needs about twice the single-run allowance.
  [ "${SCENARIO:-single}" = H ] && min=$((min * 2))
  while ! "$DATA/venv/bin/python" "$KIT/window.py" --task-min "$min"; do
    s=$("$DATA/venv/bin/python" "$KIT/window.py" --next "$min" 2>/dev/null || echo 300)
    [ "$s" -gt 300 ] && s=300                 # re-check every 5 min, so a shorter task can slip in
    echo "$(date +%H:%M) window closed for $1 (longest ${min}m); waiting ${s}s"
    sleep "$s"
  done
}

if [ -n "$VARIANTS" ]; then FIELD=$VARIANTS; else FIELD=$HARNESSES; fi
echo "$(date +%H:%M) $BATCH started: field=[$FIELD] x ($TASKLIST) x $REPS${VARIANTS:+ scenario=$SCENARIO}"
for rep in $(seq 1 "$REPS"); do
  for task in $TASKLIST; do
    for f in $FIELD; do
      if [ -n "$VARIANTS" ]; then ID="opencode-$f-$task-$rep"; else ID="$f-$task-$rep"; fi
      [ -f "$B/logs/$ID.grade.json" ] && { echo "skip $ID (graded)"; continue; }
      wait_others
      gate "$task"
      if [ -n "$VARIANTS" ]; then
        VARIANT=$f SCENARIO=$SCENARIO "$KIT/run_trial.sh" opencode "$task" "$rep"
      else
        "$KIT/run_trial.sh" "$f" "$task" "$rep"
      fi
      [ $? -eq 3 ] && { echo "$(date +%H:%M) stopped: Qwen froze"; exit 3; }
    done
  done
done
"$DATA/venv/bin/python" "$KIT/summarize.py" --notify > /dev/null
echo "$(date +%H:%M) $BATCH finished, see $DATA/$BATCH/REPORT.md"
