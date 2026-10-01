#!/bin/bash
# Offline proof that each variant actually loads: config parses, plugins resolve from the image, the
# instruction files are where the config says they are, Magic Context's config is readable, and the
# memory server comes up for the capture variants. Everything runs with --network none, so a model
# call cannot succeed and nothing leaves the container: the run is expected to fail at the model step,
# and only that failure is allowed. The container wrapper prints a `plugin-evidence` line per plugin
# that did something, which is what this script grades.
#
#   trial/check_offline.sh          # all seven variants
#   trial/check_offline.sh V3 V6    # just these
set -u
KIT=$(cd "$(dirname "$0")" && pwd)
IMAGE=${TRIAL_IMAGE:-agent-trial:5}
KEYS=${TRIAL_KEYS:-$HOME/.config/agent-trial}
MODEL=vllm-qwen3.8-nothink
VAR=${*:-V0 V1 V2 V3 V4 V5 V6}
rc=0

for V in $VAR; do
  CFG=$KIT/variants/$V.json
  [ -f "$CFG" ] || { echo "$V: MISSING $CFG"; rc=1; continue; }
  D=$(mktemp -d /tmp/offline-$V.XXXX)
  # A throwaway project: the plugins index the working directory, so a run with no /work tells us
  # nothing about them.
  W=$D/work; mkdir -p $W; git -C $W init -q 2>/dev/null; echo x > $W/README.md
  # Mount only what this variant may read, exactly as run_trial.sh does.
  MOUNTS="-v $KIT/opencode-run.sh:/opencode-run.sh:ro"
  grep -q "cheap-reads" $CFG && MOUNTS="$MOUNTS -v $KIT/cheap-reads.md:/opt/trial/cheap-reads.md:ro"
  grep -q "context-mode-AGENTS" $CFG && MOUNTS="$MOUNTS -v $KIT/context-mode-AGENTS.md:/opt/trial/context-mode-AGENTS.md:ro"
  (
    AIGATE_KEY="$(cat $KEYS/trial-opencode.key)" AIGATE_HISTORIAN_KEY="$(cat $KEYS/trial-historian.key)" \
    OPENCODE_CONFIG_CONTENT="$(cat $CFG)" OPENCODE_MODEL=$MODEL PROMPT="read README.md and stop" \
    XDG_DATA_HOME=/state/data XDG_STATE_HOME=/state/state \
    AGENTMEMORY_DATA_DIR=/state/data/agentmemory MAGIC_CONTEXT_STORAGE_DIR=/state/data/magic-context \
    timeout -k 10 240 docker run --rm --network none -w /work \
      -v $D:/state -v $W:/work $MOUNTS \
      -e XDG_DATA_HOME -e XDG_STATE_HOME -e AGENTMEMORY_DATA_DIR -e MAGIC_CONTEXT_STORAGE_DIR \
      -e AIGATE_KEY -e AIGATE_HISTORIAN_KEY -e OPENCODE_CONFIG_CONTENT -e OPENCODE_MODEL -e PROMPT \
      $IMAGE /bin/bash /opencode-run.sh "$V" > $D/run.log 2>&1
  )
  # Allowed: the model call failing (no network), OpenCode's models.dev fetch failing, AgentMemory's
  # own startup chatter. Anything about config, plugins or missing files is not allowed.
  BAD=$(grep -iE "plugin|config|instruction|schema|ENOENT|no such file|invalid|permission denied" $D/run.log \
        | grep -viE "AI_APICallError|AI_RetryError|Cannot connect to API|models\.dev|agentmemory|plugin-evidence|ProviderModelNotFound|Failed to fetch" || true)
  ok=yes; [ -n "$BAD" ] && ok=NO
  ev=$(grep -o "plugin-evidence [a-z_=0-9]*" $D/run.log | sed 's/plugin-evidence //' | tr '\n' ' ')
  # Each plugin this variant loads must appear in the evidence.
  miss=""
  grep -q "context-mode@" $CFG && { echo "$ev" | grep -q ctx_sessions || miss="$miss ctx"; }
  grep -q "magic-context" $CFG && { echo "$ev" | grep -q mc_db || miss="$miss mc"; }
  grep -q "agentmemory-capture" $CFG && {
    grep -q "memory server did not come up" $D/run.log && { miss="$miss am-down"; } \
      || { echo "$ev" | grep -q am_data || miss="$miss am_data"; }; }
  # The historian is only called once there is history to compress, so a one-step offline run cannot
  # make it: that is expected here and is proved in a real run instead (see SPEC step 5).
  if grep -q "cheap-reads" $CFG && [ ! -s $KIT/cheap-reads.md ]; then miss="$miss reads"; fi
  if grep -q "context-mode-AGENTS" $CFG && [ ! -s $KIT/context-mode-AGENTS.md ]; then miss="$miss cmtext"; fi
  if grep -q "magic-context" $CFG && [ ! -s $KIT/image/magic-context.jsonc ]; then miss="$miss mccfg"; fi
  [ -n "$miss" ] && ok=NO
  printf '%-3s %-4s evidence: %-45s missing:%s\n' "$V" "$ok" "${ev:- none}" "${miss:- -}"
  [ "$ok" = NO ] && { rc=1; echo "$BAD" | head -4 | sed 's/^/     /'; }
  rm -rf $D
done
exit $rc
