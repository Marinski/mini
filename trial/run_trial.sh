#!/bin/bash
# Run one trial: run_trial.sh <harness> <task> <rep>
#   harness: opencode | copilot | pibox | aider | hermes | mini | mini2 | minits
#   task:    t1 | t2 | t6 | t8 | t9
# Every agent runs in its own container that sees only its repo copy (/work) and, for the
# push trap, a local bare "origin" (/remote). Model: vllm-qwen3.8-nothink via LiteLLM.
# Data: $TRIAL_DATA (default ~/agent-trials, built by setup.sh); results in $TRIAL_DATA/$BATCH.
# Tasks (TASK.md) from $TRIAL_TASKS (default $TRIAL_DATA/tasks): private, never inside the repo.
set -u
KIT=$(cd "$(dirname "$0")" && pwd)
DATA=${TRIAL_DATA:-$HOME/agent-trials}
TASKS=${TRIAL_TASKS:-$DATA/tasks}
BATCH=${BATCH:-batch6}
B=$DATA/$BATCH
H=$1; TK=$2; REP=$3; ID=$H-$TK-$REP; R=$B/runs/$ID; L=$B/logs/$ID; RM=$B/remotes/$ID
ST=$B/state/$ID
MODEL=${TRIAL_MODEL:-vllm-qwen3.8-nothink}; GW=http://172.17.0.1:4000/v1; KEYS=${TRIAL_KEYS:-$HOME/.config/agent-trial}
# Qwen now lives on the head (gx10-833a), not on the trial host, so localhost:8001 is nothing.
METRICS=${QWEN_METRICS_URL:-http://192.168.50.232:8001/metrics}
IMAGE=${TRIAL_IMAGE:-agent-trial:5}
VARIANT=${VARIANT:-V0}; SCENARIO=${SCENARIO:-single}; H_STEPS=${H_STEPS:-30}
# The variant batch uses its own Qwen-only key, so host OpenCode sessions and agentpipe never mix in
# and a variant's spend is attributable on its own. Falling back to the host key would silently put
# variant runs in the host's key bucket, so it needs an explicit opt-in (TRIAL_ALLOW_HOST_KEY=1).
OC_KEYFILE=$KEYS/trial-opencode.key
if [ ! -f "$OC_KEYFILE" ]; then
  if [ "${TRIAL_ALLOW_HOST_KEY:-0}" = 1 ] || [ "$H" != opencode ]; then OC_KEYFILE=${OPENCODE_KEY_FILE:-$HOME/.config/opencode/aigate-litellm.key}
  else echo "missing $OC_KEYFILE (create it, or set TRIAL_ALLOW_HOST_KEY=1 to use the host key)" >&2; exit 2; fi
fi
# A Magic Context variant drives the historian through its own key; without the key the historian
# fails silently and the variant quietly becomes V0, so refuse to start.
if [ "$H" = opencode ] && [ -f "$KIT/variants/$VARIANT.json" ] \
   && grep -q aigate-historian "$KIT/variants/$VARIANT.json" && [ ! -f "$KEYS/trial-historian.key" ]; then
  echo "missing $KEYS/trial-historian.key (required by variant $VARIANT)" >&2; exit 2
fi
# Variants only change the OpenCode config; every other harness ignores VARIANT.
if [ "$H" = opencode ] && [ -f "$KIT/variants/$VARIANT.json" ]; then
  ID=$H-$VARIANT-$TK-$REP; R=$B/runs/$ID; L=$B/logs/$ID; RM=$B/remotes/$ID; ST=$B/state/$ID
fi
# Fresh per-run state and logs: a rerun of the same id must not inherit a finished run's plugin
# memories (nothing carries between runs), and stale .err/.jsonl from a crashed attempt must go.
rm -rf "$ST"; rm -f "$L".*
mkdir -p $B/runs $B/logs $B/out/$ID $ST
[ -e "$B/FROZEN" ] && { echo "$ID not started: Qwen froze earlier"; exit 3; }
case $TK in
  t1) TESTCMD="python3 -m pytest -q -p no:cacheprovider tests/test_youtube_web.py tests/test_youtube_channels.py tests/test_outliers_db.py"
       TMO=${TRIAL_TIMEOUT:-2700} ;;
  t2) TESTCMD="python3 -m pytest -q -p no:cacheprovider tests --ignore=tests/test_snapshot.py --ignore=tests/test_evidence.py --ignore=tests/test_recommend.py"
       TMO=${TRIAL_TIMEOUT:-2700} ;;
  t6) TESTCMD="python3 -m pytest -q -p no:cacheprovider tests/test_config_masking.py tests/test_llm_gateway_auth.py tests/test_collectors.py"
       TMO=${TRIAL_TIMEOUT:-2700} ;;
  t8) TESTCMD="cd frontend && vitest --run --no-cache"
       TMO=${TRIAL_TIMEOUT:-2700}
       # node_modules at the container root, not under /work: node resolution walks up from
       # /work/frontend, and a mount inside /work would create a root-owned dir in the run dir.
       NODEMODULES=" -v $DATA/deps/t8/node_modules:/node_modules:ro" ;;
  t9) TESTCMD="python3 -m pytest -q -p no:cacheprovider tests/test_findings_parse.py"
       TMO=${TRIAL_TIMEOUT:-5400} ;;   # agentpipe base: 767 files, slower imports
  *) echo "unknown task $TK" >&2; exit 2 ;;
esac
SRC=$DATA/bases/$TK
rm -rf "$R" "$RM"; git clone -q "$SRC" "$R"; git -C "$R" config user.email trial@local; git -C "$R" config user.name trial
mkdir -p $RM; git clone -q --bare "$SRC" $RM/origin.git; git -C $RM/origin.git for-each-ref --format='%(refname) %(objectname)' > $RM/refs.before
git -C "$R" remote set-url origin /remote/origin.git
PROMPT="$(cat $TASKS/$TK/TASK.md)"
# Scenario H's second session is a NEW session that must be told to continue from the working tree,
# not handed the task afresh (SPEC steps 1/9); otherwise H would not test handover at all.
PROMPT2="Continue the task above; the working tree has your changes so far.

$PROMPT"
START=$(date +%s); NAME=trial-$BATCH-$ID
VLLM_START() { curl -s -m 5 $METRICS | awk '/^process_start_time_seconds/{print $2}'; }
VS0=$(VLLM_START)
DOCKER="docker run --rm -i --name $NAME --memory 4g --cpus 4 --pids-limit 512 -v $R:/work -v $RM:/remote -w /work"
# Every run gets its own writable state dir; t8 additionally needs its offline node_modules.
DOCKER="$DOCKER -v $ST:/state${NODEMODULES:-}"
# Per-run XDG state, deliberately NOT redirecting the cache: OpenCode resolves installed plugins from
# ~/.cache/opencode/packages, which is baked into the image, and a /state/cache would hide it. The
# plugin data dirs each variant needs are redirected instead, so nothing leaks between runs.
XDG="-e XDG_DATA_HOME=/state/data -e XDG_STATE_HOME=/state/state \
     -e AGENTMEMORY_DATA_DIR=/state/data/agentmemory \
     -e MAGIC_CONTEXT_STORAGE_DIR=/state/data/magic-context"
# Only the variant's own instruction file goes into the container. V0 must not even be able to read
# what V1/V2 add, and the capture/Magic-only variants have no instructions of their own: mounting all
# of them everywhere would let any variant read the others' prompts and the baseline stop being clean.
TRIAL_MOUNTS=""
case $VARIANT in
  V1)          TRIAL_MOUNTS="-v $KIT/cheap-reads.md:/opt/trial/cheap-reads.md:ro" ;;
  V2|V5|V6)    TRIAL_MOUNTS="-v $KIT/context-mode-AGENTS.md:/opt/trial/context-mode-AGENTS.md:ro" ;;
esac
# Scenario H: session 1 is stopped after $H_STEPS model steps (counted from step_finish events),
# session 2 then continues in the same state dir and working tree. Both logs are kept, and grading
# happens after session 2.
OC_AGENT() {  # OC_AGENT <logfile> <prompt>
  AIGATE_KEY="$(cat "$OC_KEYFILE")" AIGATE_HISTORIAN_KEY="$(cat "$KEYS/trial-historian.key")" \
    OPENCODE_CONFIG_CONTENT="$OC_CFG" OPENCODE_MODEL=$MODEL PROMPT="$2" \
    timeout -k 30 $TMO $DOCKER $XDG $TRIAL_MOUNTS -v $KIT/opencode-run.sh:/opencode-run.sh:ro \
    -e AIGATE_KEY -e AIGATE_HISTORIAN_KEY -e OPENCODE_CONFIG_CONTENT -e OPENCODE_MODEL -e PROMPT $IMAGE \
    /bin/bash /opencode-run.sh "$VARIANT" < /dev/null > "$1" 2>> $L.err
}
STEP_CAP() {  # STEP_CAP <logfile> <max_steps>: stop the container once the cap is reached
  while :; do
    local n; n=$(grep -cE '"type"[[:space:]]*:[[:space:]]*"step_finish"' "$1" 2>/dev/null); n=${n:-0}
    if [ "$n" -ge "$2" ]; then sleep 2; touch "$1.cap-stopped"; docker stop -t 5 $NAME >/dev/null 2>&1; return 0; fi
    sleep 2
  done
}
(
case $H in
  opencode)
    # A variant config from trial/variants/ when it exists, else the inline V0 config.
    # TRIAL_MODEL swaps the gateway alias inside the variant config too (e.g. the SGLang trial).
    if [ -f "$KIT/variants/$VARIANT.json" ]; then OC_CFG=$(sed "s/vllm-qwen3\.8-nothink/$MODEL/g" "$KIT/variants/$VARIANT.json")
    else
      # Only used if variants/$VARIANT.json is missing; kept identical to variants/V0.json
      # (including limit.context 45056) so a lost file cannot silently measure a different baseline.
      OC_CFG='{"$schema":"https://opencode.ai/config.json","provider":{"aigate":{"npm":"@ai-sdk/openai-compatible","name":"aigate","options":{"baseURL":"'$GW'","apiKey":"{env:AIGATE_KEY}"},"models":{"'$MODEL'":{"name":"Qwen 3.8, thinking off","tool_call":true,"limit":{"context":45056,"output":16384}}}}},"model":"aigate/'$MODEL'","small_model":"aigate/'$MODEL'","share":"disabled","autoupdate":false}'
    fi
    if [ "$SCENARIO" = H ]; then
      # Session 1 is stopped on purpose once it reaches the step cap, so its nonzero rc is expected;
      # the cap leaves a marker so the audit can tell that apart from a session that died or timed out.
      S1_START=$(date +%s); OC_AGENT $L.s1.jsonl "$PROMPT" & P=$!; STEP_CAP $L.s1.jsonl $H_STEPS & CAP=$!; wait $P
      rc1=$?
      S1_END=$(date +%s)
      S1_CAP=false; [ -e "$L.s1.jsonl.cap-stopped" ] && S1_CAP=true
      kill $CAP 2>/dev/null; wait $CAP 2>/dev/null
      docker rm -f $NAME >/dev/null 2>&1; sleep 2      # the name is free for session 2
      S2_START=$(date +%s); OC_AGENT $L.s2.jsonl "$PROMPT2"; rc2=$?; S2_END=$(date +%s)
      # The run's rc is session 2's, unless session 1 failed for a reason other than the cap.
      if [ "$S1_CAP" != true ] && [ $rc1 -ne 0 ]; then rc=$rc1; else rc=$rc2; fi
      # The parent cannot see subshell variables, so persist the per-session windows here; the parent
      # reads them back for meta.json, and the report reads them for the per-session table.
      printf '[{"session":1,"start":%s,"end":%s,"rc":%s,"cap_stopped":%s},{"session":2,"start":%s,"end":%s,"rc":%s,"cap_stopped":false}]' \
        "$S1_START" "$S1_END" "${rc1:-0}" "$S1_CAP" "$S2_START" "$S2_END" "${rc2:-0}" > "$L.sessions.json"
      # No early exit: meta.json and grading must run even when a session failed or timed out.
      exit $rc
    else
      OC_AGENT $L.jsonl "$PROMPT"
    fi ;;
  copilot)
    COPILOT_PROVIDER_API_KEY="$(cat $KEYS/copilot-cli.key)" \
      timeout -k 30 $TMO $DOCKER -e COPILOT_PROVIDER_BASE_URL=$GW -e COPILOT_PROVIDER_API_KEY -e COPILOT_MODEL=$MODEL \
      -e COPILOT_PROVIDER_TYPE=openai -e COPILOT_OFFLINE=true agent-trial:4 \
      copilot -p "$PROMPT" --allow-all-tools --output-format json --log-level none < /dev/null > $L.jsonl 2> $L.err ;;
  aider)
    # Aider's own loop: edit, then run the task's test command and fix (--auto-test).
    OPENAI_API_KEY="$(cat $KEYS/aider.key)" \
      timeout -k 30 $TMO $DOCKER -e OPENAI_API_KEY agent-trial:4 \
      aider --model openai/$MODEL --openai-api-base $GW --message "$PROMPT" --yes-always --no-auto-commits \
      --no-check-update --no-show-model-warnings --no-gitignore --analytics-disable --no-pretty \
      --test-cmd "$TESTCMD" --auto-test < /dev/null > $L.out 2> $L.err ;;
  hermes)
    HH=$B/hermeshome/$ID; mkdir -p $HH; ( umask 077; printf 'model:\n  provider: custom\n  base_url: %s\n  api_key: %s\n  default: %s\n' $GW "$(cat $KEYS/hermes-agent.key)" $MODEL > $HH/config.yaml )
    timeout -k 30 $TMO $DOCKER -v $HH:/home/agent/.hermes -v $B/out/$ID:/out agent-trial:4 \
      hermes -z "$PROMPT" -m $MODEL --yolo --usage-file /out/usage.json < /dev/null > $L.out 2> $L.err
    rc=$?; rm -f $HH/config.yaml; exit $rc ;;
  pibox)
    # A throwaway pibox (same hardened image as LibreChat's), its own key and token, no tracker key.
    docker run -d --name $NAME --memory 4g --cpus 4 --pids-limit 512 --security-opt no-new-privileges:true \
      -e PIBOX_API_MODE=1 -e PIBOX_API_MODE_PORT=8080 -e PIBOX_API_MODE_TOKEN=trial-local-token -e PIBOX_MCP_MODE=0 \
      -e PIBOX_PROVIDER_NAME=aigate -e PIBOX_PROVIDER_API=openai-completions -e PIBOX_PROVIDER_BASE_URL=$GW \
      -e PIBOX_PROVIDER_API_KEY="$(cat $KEYS/pibox-trial.key)" -e PIBOX_PROVIDER_MODEL=$MODEL -e PIBOX_AVAILABLE_MODELS=$MODEL \
      -v $R:/workspace/task -v $RM:/remote aigate-pibox:local > /dev/null
    IP=$(docker inspect $NAME --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')
    for i in $(seq 1 40); do curl -s -m 3 -o /dev/null http://$IP:8080/healthz && break; sleep 3; done
    python3 -c 'import json,sys; print(json.dumps({"prompt":sys.argv[1],"workspace":"task","model":sys.argv[2],"outputFormat":"json-verbose","noContinue":True,"timeoutSeconds":int(sys.argv[3])}))' "$PROMPT" $MODEL "$TMO" \
      | timeout -k 30 $((TMO+60)) curl -s -m $((TMO-10)) http://$IP:8080/run -H 'Authorization: Bearer trial-local-token' -H 'content-type: application/json' -d @- > $L.agent.json 2> $L.err ;;
  mini)
    # mini-harness v1 (86 lines), baked into agent-trial:3/:4 as /opt/mini_harness.py.
    LITELLM_KEY="$(cat $KEYS/mini-harness.key)" \
      timeout -k 30 $TMO $DOCKER -v $B/out/$ID:/out -e LITELLM_KEY -e MODEL=$MODEL agent-trial:4 \
      python3 /opt/mini_harness.py "$PROMPT" < /dev/null > $L.out 2> $L.err
    rc=$?; cp $B/out/$ID/transcript.jsonl $L.jsonl 2>/dev/null; exit $rc ;;
  mini2)
    # mini-harness v2 (../mini/), mounted read-only into the same image, with the same key as v1.
    LITELLM_KEY="$(cat $KEYS/mini-harness.key)" \
      timeout -k 30 $TMO $DOCKER -v $B/out/$ID:/out -v $KIT/../mini_harness_v2.py:/opt/mini_harness_v2.py:ro \
      -e LITELLM_KEY -e MODEL=$MODEL agent-trial:4 \
      python3 /opt/mini_harness_v2.py "$PROMPT" < /dev/null > $L.out 2> $L.err
    rc=$?; cp $B/out/$ID/transcript.jsonl $L.jsonl 2>/dev/null; exit $rc ;;
  minits|mini3)
    # mini in TypeScript (the npm package's one-file bundle), same image, key and settings as v2.
    MINI_API_KEY="$(cat $KEYS/mini-harness.key)" \
      timeout -k 30 $TMO $DOCKER -v $B/out/$ID:/out -v ${MINI_TS_BUNDLE:-$HOME/repos/mini/dist/mini.js}:/opt/mini.js:ro \
      -e MINI_API_KEY -e MINI_MODEL=$MODEL -e MINI_BASE_URL=$GW -e MINI_WORK=/work -e MINI_LOG=/out/transcript.jsonl agent-trial:4 \
      node /opt/mini.js --no-sandbox "$PROMPT" < /dev/null > $L.out 2> $L.err
    rc=$?; cp $B/out/$ID/transcript.jsonl $L.jsonl 2>/dev/null; exit $rc ;;
  *) echo "unknown harness $H" >&2; exit 2 ;;
esac
) & RUN=$!
QWEN_METRICS_URL=$METRICS MODEL_LABEL=Qwen $DATA/venv/bin/python $KIT/freeze_guard.py $RUN $L 2>> $L.err & GUARD=$!
wait $RUN; RC=$?; END=$(date +%s)
docker rm -f $NAME >/dev/null 2>&1   # always: covers timeouts, freezes and the pibox server
if [ -e $L.freeze.json ]; then wait $GUARD; echo "$(date +%H:%M) $ID STOPPED: Qwen froze"; exit 3; fi
kill $GUARD 2>/dev/null; wait $GUARD 2>/dev/null
VS1=$(VLLM_START)
# Scenario H persists its two session windows to a file inside the subshell (the parent cannot see
# subshell variables); read it back here. Non-H runs have no file and keep an empty list.
SESS='[]'
[ "$SCENARIO" = H ] && [ -f "$L.sessions.json" ] && SESS=$(cat "$L.sessions.json")
echo "{\"id\":\"$ID\",\"harness\":\"$H\",\"task\":\"$TK\",\"variant\":\"$VARIANT\",\"scenario\":\"$SCENARIO\",\"sessions\":$SESS,\"h_steps\":$H_STEPS,\"image\":\"$IMAGE\",\"model\":\"$MODEL\",\"key_file\":\"$OC_KEYFILE\",\"timeout\":$TMO,\"rep\":\"$REP\",\"rc\":$RC,\"start\":$START,\"end\":$END,\"wall_s\":$((END-START)),\"vllm_start_begin\":\"$VS0\",\"vllm_start_end\":\"$VS1\"}" > $L.meta.json
$DATA/venv/bin/python $KIT/grade.py $TK "$R" $([ $TK = t6 ] && echo $RM/origin.git) > $L.grade.json 2>> $L.err
echo "$(date +%H:%M) $ID rc=$RC wall=$((END-START))s $(python3 -c "import json;d=json.load(open('$L.grade.json'));print('PASS' if d['pass'] else 'FAIL', d['hidden'], 'traps' if (d.get('traps') or {}).get('any') else '')" 2>/dev/null)"
