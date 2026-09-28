#!/bin/bash
# Run harnesses x tasks x reps one at a time, then build the report and post it to Discord.
# Usage: BATCH=batch6 queue.sh "<harness ...>" [reps] [tasks]     e.g. queue.sh "mini2" 3 "t1 t2 t6"
# Start it with nohup/setsid and append to $TRIAL_DATA/$BATCH/batch.log.
KIT=$(cd "$(dirname "$0")" && pwd)
DATA=${TRIAL_DATA:-$HOME/agent-trials}
export BATCH=${BATCH:-batch6}
HARNESSES=$1; REPS=${2:-3}; TASKLIST=${3:-"t1 t2 t6"}
# Never share Qwen (or a key) with another trial run: wait for any running one to end.
# (anchored to "bash <path>" so a shell that merely mentions the path doesn't count)
while pgrep -f '^(/usr)?(/bin/)?bash /\S*/harness/trial/(run_trial|queue)\.sh' | grep -vx "$$" >/dev/null; do sleep 30; done
echo "$(date +%H:%M) $BATCH started: $HARNESSES x ($TASKLIST) x $REPS"
for rep in $(seq 1 "$REPS"); do
  for task in $TASKLIST; do
    for h in $HARNESSES; do
      "$KIT/run_trial.sh" "$h" "$task" "$rep"
      [ $? -eq 3 ] && { echo "$(date +%H:%M) stopped: Qwen froze"; exit 3; }
    done
  done
done
"$DATA/venv/bin/python" "$KIT/summarize.py" --notify > /dev/null
echo "$(date +%H:%M) $BATCH finished, see $DATA/$BATCH/REPORT.md"
