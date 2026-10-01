#!/bin/bash
# Scenario H control-flow test, no model calls and no docker.
#
# It slices the H block out of run_trial.sh itself rather than keeping a copy here, so the test cannot
# drift from what the runner actually executes: if the block moves or loses a line, the slice fails
# loudly instead of quietly testing nothing. OC_AGENT and STEP_CAP are stubbed, and the slice runs in a
# subshell exactly as run_trial.sh runs its case statement, so the block's own return value is what
# gets checked.
#
# The stubs keep the real timing that the rc logic depends on: the capped session does not return
# until the cap marker exists, because in the real runner the container keeps running until
# STEP_CAP's "docker stop" lands. A stub that returned the moment it wrote its log would let the
# parent read the marker before the cap wrote it, and the test would pass on a runner that loses it.
#
# What it proves, per case:
#   1. both sessions are attempted even when session 1 dies, so the parent still writes meta.json and
#      grades the run instead of the run vanishing from the report;
#   2. a cap-stopped session 1 with a nonzero rc is not a failure - the run follows session 2;
#   3. an uncapped session-1 failure decides the run's rc;
#   4. the block returns that rc, because the parent turns it into meta.json's "rc" and into the line
#      the operator reads. A block ending on a variable assignment returns 0 and lies about every H run.
set -u
KIT=$(cd "$(dirname "$0")" && pwd)
FAILED=0
ok()  { echo "ok  $1"; }
bad() { echo "FAIL  $1"; FAILED=$((FAILED+1)); }

# The slice: from the H branch to the "fi ;;" that closes it. The trailing " ;;" belongs to the case
# statement the block sits in, so it is dropped, and the leading four spaces come off so the block can
# be eval'd on its own.
BLOCK=$(sed -n '/^    if \[ "\$SCENARIO" = H \]; then$/,/^    fi ;;$/p' "$KIT/run_trial.sh" \
  | sed 's/^    //; s/^fi ;;$/fi/')
case $BLOCK in
  *'if [ "$SCENARIO" = H ]; then'*) ;;
  *) echo "FAIL  the scenario-H branch is no longer where this test looks for it in run_trial.sh"; exit 1 ;;
esac
# Exactly one exit, and it has to be the last statement of the H branch: an exit earlier would skip
# session 2 and the parent would never reach meta.json. The branch's own "else"/"fi" may follow it.
EXITS=$(printf '%s\n' "$BLOCK" | grep -c '^ *exit ')
NEXT=$(printf '%s\n' "$BLOCK" | grep -A1 '^ *exit ' | tail -1 | sed 's/^ *//')
if [ "$EXITS" -ne 1 ] || { [ "$NEXT" != else ] && [ "$NEXT" != fi ]; }; then
  # The likely cause is the return being dropped: the subshell would then end on the rc assignment and
  # report success for every H run, which is the bug this check exists for.
  bad "the H branch must exit exactly once with \$rc, as its last statement (found $EXITS exits, followed by [$NEXT])"
fi

# scenario <name> <cap steps> <s1 steps> <s1 rc> <s2 steps> <s2 rc> <expected run rc>
scenario() {
  local name=$1 cap=$2 s1n=$3 s1rc=$4 s2n=$5 s2rc=$6 want=$7
  local dir; dir=$(mktemp -d)
  L=$dir/logs; H_STEPS=$cap; NAME=h-fixture; SCENARIO=H
  # The block passes the task prompt to session 1 and the handover prompt to session 2 (SPEC step 9).
  PROMPT=task; PROMPT2="continue"
  local capped=false; [ "$s1n" -ge "$cap" ] && capped=true
  # Which session this is comes from the log file name, not a counter: session 1 runs in a background
  # subshell, so a counter incremented inside it would be lost by the time session 2 runs in the parent.
  # The name is matched as a glob, since the log is "$L.s1.jsonl" and parameter expansion cannot pull
  # the middle field out of it.
  OC_AGENT() {  # OC_AGENT <logfile>
    local n rc i
    case $1 in
      *.s1.jsonl) n=$s1n; rc=$s1rc ;;
      *)          n=$s2n; rc=$s2rc ;;
    esac
    for i in $(seq 1 "$n"); do echo '{"type":"step_finish"}' >> "$1"; done
    # A capped session is stopped from outside, so it must not return before the marker is written.
    if [ "$capped" = true ]; then
      case $1 in *.s1.jsonl) for i in $(seq 1 300); do [ -e "$1.cap-stopped" ] && break; sleep 0.1; done ;; esac
    fi
    return $rc
  }
  STEP_CAP() {  # STEP_CAP <logfile> <max_steps>: polls, marks, stops - the real one never exits early
    local n i
    for i in $(seq 1 300); do
      n=$(grep -c '"type":"step_finish"' "$1" 2>/dev/null); n=${n:-0}
      if [ "$n" -ge "$2" ]; then sleep 0.2; touch "$1.cap-stopped"; return 0; fi
      sleep 0.1
    done
  }
  local got problems=""
  ( eval "$BLOCK" ) >/dev/null 2>&1; got=$?
  [ "$got" = "$want" ] || problems="run rc was $got, expected $want"
  [ -e "$L.s1.jsonl" ] || problems="$problems; session 1 left no log"
  [ -e "$L.s2.jsonl" ] || problems="$problems; session 2 left no log"
  if [ "$capped" = true ]; then
    [ -e "$L.s1.jsonl.cap-stopped" ] || problems="$problems; capped session left no marker"
  else
    [ -e "$L.s1.jsonl.cap-stopped" ] && problems="$problems; marker without a cap"
  fi
  rm -rf "$dir"
  if [ -z "$problems" ]; then ok "$name"; else bad "$name:$problems"; fi
}

scenario "cap stop, clean second session"      2  2 137  1 0   0    # the cap's 137 is not a failure
scenario "cap stop, second session times out"  2  2 137  1 124 124  # the timeout is the run's rc
scenario "session 1 dies without the cap"      9  2 137  1 0   137  # an uncapped failure decides
scenario "s1 uncapped failure, s2 also fails"  9  1 1    1 1   1
scenario "both sessions clean"                 1  1 0    1 0   0

[ $FAILED = 0 ] && echo "scenario-H control flow: all as expected" || { echo "scenario-H control flow: FAILED"; exit 1; }
