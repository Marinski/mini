#!/bin/bash
# Container-side entry point for one OpenCode trial run, mounted read-only by run_trial.sh.
#   args:   $1 = variant (V0..V6)
#   env:    OPENCODE_CONFIG_CONTENT, AIGATE_KEY, OPENCODE_MODEL, PROMPT
# The host applies the timeout (timeout -k 30 $TMO docker run ...), so this script does not.
set -u
VARIANT=$1
MODEL=${OPENCODE_MODEL:-vllm-qwen3.8-nothink}
# The plugins write into the run's own state dir; create it up front so a plugin that indexes
# something during startup cannot trip over a missing parent.
mkdir -p "${XDG_DATA_HOME:-/state/data}" "${XDG_STATE_HOME:-/state/state}" \
         "${AGENTMEMORY_DATA_DIR:-/state/data/agentmemory}" \
         "${MAGIC_CONTEXT_STORAGE_DIR:-/state/data/magic-context}"

# The capture plugin only observes; it POSTs each hook to the memory server on :3111. Variants that
# load it therefore need that server up first, backed by the per-run state dir. Everything is
# baked in the image (iii engine, MiniLM), so nothing here needs the network.
case $VARIANT in
  V4|V6)
    agentmemory > /state/agentmemory.log 2>&1 &
    AM_PID=$!
    up=0
    for _ in $(seq 1 30); do
      sleep 2
      if node -e 'fetch("http://127.0.0.1:3111/agentmemory/status").then(r=>process.exit(0)).catch(()=>process.exit(1))' 2>/dev/null; then
        # /status answers 404 on this build; the port answering at all is what matters, and the
        # capture path itself is POST /agentmemory/observe.
        if node -e 'fetch("http://127.0.0.1:3111/agentmemory/observe",{method:"POST",headers:{"content-type":"application/json"},body:"{}"}).then(r=>process.exit(r.status<500?0:1)).catch(()=>process.exit(1))' 2>/dev/null; then
          up=1; break
        fi
      fi
    done
    if [ $up -ne 1 ]; then
      echo "memory server did not come up on :3111" >&2
      sed -n '1,20p' /state/agentmemory.log >&2
      kill $AM_PID 2>/dev/null
      exit 4
    fi ;;
esac

opencode run --auto --dir /work -m aigate/$MODEL --format json "$PROMPT" < /dev/null
rc=$?

# Plugin evidence, so check_offline.sh can prove each plugin did something instead of inferring it
# from a clean exit. ContextMode keeps its session dbs in its own config dir (no env override, and the
# container's own layer is fresh per run); Magic Context and AgentMemory write to the run's state dir.
# The memory server writes asynchronously and is still running here, so give it a few seconds before
# looking and read the evidence before stopping it.
am=0
for _ in $(seq 1 10); do
  if [ -n "${AGENTMEMORY_DATA_DIR:-}" ] && [ -n "$(ls -A "$AGENTMEMORY_DATA_DIR" 2>/dev/null)" ]; then
    am=1; break
  fi
  [ -n "${AM_PID:-}" ] || break
  sleep 1
done
ctx=$(find /home/agent/.config/opencode/context-mode/sessions -name '*.db' 2>/dev/null | wc -l)
[ "$ctx" -gt 0 ] && echo "plugin-evidence ctx_sessions=$ctx"
[ -n "${MAGIC_CONTEXT_STORAGE_DIR:-}" ] && [ -f "$MAGIC_CONTEXT_STORAGE_DIR/context.db" ] \
  && echo "plugin-evidence mc_db=yes"
[ "$am" = 1 ] && echo "plugin-evidence am_data=yes"
[ -n "${AM_PID:-}" ] && { kill $AM_PID 2>/dev/null; wait $AM_PID 2>/dev/null; }
exit $rc
