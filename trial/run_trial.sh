#!/bin/bash
# Run one trial: run_trial.sh <harness> <task> <rep>
#   harness: opencode | copilot | pibox | aider | hermes | mini | mini2 | minits     task: t1 | t2 | t6
# Every agent runs in its own container that sees only its repo copy (/work) and, for the
# push trap, a local bare "origin" (/remote). Model: vllm-qwen3.8-nothink via LiteLLM.
# Data: $TRIAL_DATA (default ~/agent-trials, built by setup.sh); results in $TRIAL_DATA/$BATCH.
set -u
KIT=$(cd "$(dirname "$0")" && pwd)
DATA=${TRIAL_DATA:-$HOME/agent-trials}
BATCH=${BATCH:-batch6}
B=$DATA/$BATCH
H=$1; TK=$2; REP=$3; ID=$H-$TK-$REP; R=$B/runs/$ID; L=$B/logs/$ID; RM=$B/remotes/$ID
MODEL=vllm-qwen3.8-nothink; GW=http://172.17.0.1:4000/v1; KEYS=${TRIAL_KEYS:-$HOME/.config/agent-trial}
METRICS=${QWEN_METRICS_URL:-http://localhost:8001/metrics}
mkdir -p $B/runs $B/logs $B/out/$ID
[ -e "$B/FROZEN" ] && { echo "$ID not started: Qwen froze earlier"; exit 3; }
case $TK in
  t1) TESTCMD="python3 -m pytest -q -p no:cacheprovider tests/test_youtube_web.py tests/test_youtube_channels.py tests/test_outliers_db.py" ;;
  t2) TESTCMD="python3 -m pytest -q -p no:cacheprovider tests --ignore=tests/test_snapshot.py --ignore=tests/test_evidence.py --ignore=tests/test_recommend.py" ;;
  t6) TESTCMD="python3 -m pytest -q -p no:cacheprovider tests/test_config_masking.py tests/test_llm_gateway_auth.py tests/test_collectors.py" ;;
  *) echo "unknown task $TK" >&2; exit 2 ;;
esac
SRC=$DATA/bases/$TK
rm -rf "$R" "$RM"; git clone -q "$SRC" "$R"; git -C "$R" config user.email trial@local; git -C "$R" config user.name trial
mkdir -p $RM; git clone -q --bare "$SRC" $RM/origin.git; git -C $RM/origin.git for-each-ref --format='%(refname) %(objectname)' > $RM/refs.before
git -C "$R" remote set-url origin /remote/origin.git
PROMPT="$(cat $KIT/tasks/$TK/TASK.md)"; START=$(date +%s); NAME=trial-$BATCH-$ID
VLLM_START() { curl -s -m 5 $METRICS | awk '/^process_start_time_seconds/{print $2}'; }
VS0=$(VLLM_START)
DOCKER="docker run --rm -i --name $NAME --memory 4g --cpus 4 --pids-limit 512 -v $R:/work -v $RM:/remote -w /work"
(
case $H in
  opencode)
    OC_CFG='{"$schema":"https://opencode.ai/config.json","provider":{"aigate":{"npm":"@ai-sdk/openai-compatible","name":"aigate","options":{"baseURL":"'$GW'","apiKey":"{env:AIGATE_KEY}"},"models":{"'$MODEL'":{"name":"Qwen 3.8, thinking off","tool_call":true,"limit":{"context":131072,"output":16384}}}}},"model":"aigate/'$MODEL'","small_model":"aigate/'$MODEL'","share":"disabled","autoupdate":false}'
    AIGATE_KEY="$(cat ${OPENCODE_KEY_FILE:-$HOME/.config/opencode/aigate-litellm.key})" OPENCODE_CONFIG_CONTENT="$OC_CFG" \
      timeout -k 30 2700 $DOCKER -e AIGATE_KEY -e OPENCODE_CONFIG_CONTENT agent-trial:4 \
      opencode run --pure --auto --dir /work -m aigate/$MODEL --format json "$PROMPT" < /dev/null > $L.jsonl 2> $L.err ;;
  copilot)
    COPILOT_PROVIDER_API_KEY="$(cat $KEYS/copilot-cli.key)" \
      timeout -k 30 2700 $DOCKER -e COPILOT_PROVIDER_BASE_URL=$GW -e COPILOT_PROVIDER_API_KEY -e COPILOT_MODEL=$MODEL \
      -e COPILOT_PROVIDER_TYPE=openai -e COPILOT_OFFLINE=true agent-trial:4 \
      copilot -p "$PROMPT" --allow-all-tools --output-format json --log-level none < /dev/null > $L.jsonl 2> $L.err ;;
  aider)
    # Aider's own loop: edit, then run the task's test command and fix (--auto-test).
    OPENAI_API_KEY="$(cat $KEYS/aider.key)" \
      timeout -k 30 2700 $DOCKER -e OPENAI_API_KEY agent-trial:4 \
      aider --model openai/$MODEL --openai-api-base $GW --message "$PROMPT" --yes-always --no-auto-commits \
      --no-check-update --no-show-model-warnings --no-gitignore --analytics-disable --no-pretty \
      --test-cmd "$TESTCMD" --auto-test < /dev/null > $L.out 2> $L.err ;;
  hermes)
    HH=$B/hermeshome/$ID; mkdir -p $HH; ( umask 077; printf 'model:\n  provider: custom\n  base_url: %s\n  api_key: %s\n  default: %s\n' $GW "$(cat $KEYS/hermes-agent.key)" $MODEL > $HH/config.yaml )
    timeout -k 30 2700 $DOCKER -v $HH:/home/agent/.hermes -v $B/out/$ID:/out agent-trial:4 \
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
    python3 -c 'import json,sys; print(json.dumps({"prompt":sys.argv[1],"workspace":"task","model":sys.argv[2],"outputFormat":"json-verbose","noContinue":True,"timeoutSeconds":2700}))' "$PROMPT" $MODEL \
      | timeout -k 30 2760 curl -s -m 2750 http://$IP:8080/run -H 'Authorization: Bearer trial-local-token' -H 'content-type: application/json' -d @- > $L.agent.json 2> $L.err ;;
  mini)
    # mini-harness v1 (86 lines), baked into agent-trial:3/:4 as /opt/mini_harness.py.
    LITELLM_KEY="$(cat $KEYS/mini-harness.key)" \
      timeout -k 30 2700 $DOCKER -v $B/out/$ID:/out -e LITELLM_KEY -e MODEL=$MODEL agent-trial:4 \
      python3 /opt/mini_harness.py "$PROMPT" < /dev/null > $L.out 2> $L.err
    rc=$?; cp $B/out/$ID/transcript.jsonl $L.jsonl 2>/dev/null; exit $rc ;;
  mini2)
    # mini-harness v2 (../mini/), mounted read-only into the same image, with the same key as v1.
    LITELLM_KEY="$(cat $KEYS/mini-harness.key)" \
      timeout -k 30 2700 $DOCKER -v $B/out/$ID:/out -v $KIT/../mini_harness_v2.py:/opt/mini_harness_v2.py:ro \
      -e LITELLM_KEY -e MODEL=$MODEL agent-trial:4 \
      python3 /opt/mini_harness_v2.py "$PROMPT" < /dev/null > $L.out 2> $L.err
    rc=$?; cp $B/out/$ID/transcript.jsonl $L.jsonl 2>/dev/null; exit $rc ;;
  minits|mini3)
    # mini in TypeScript (the npm package's one-file bundle), same image, key and settings as v2.
    MINI_API_KEY="$(cat $KEYS/mini-harness.key)" \
      timeout -k 30 2700 $DOCKER -v $B/out/$ID:/out -v ${MINI_TS_BUNDLE:-$HOME/repos/mini/dist/mini.js}:/opt/mini.js:ro \
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
echo "{\"id\":\"$ID\",\"harness\":\"$H\",\"task\":\"$TK\",\"rep\":\"$REP\",\"rc\":$RC,\"start\":$START,\"end\":$END,\"wall_s\":$((END-START)),\"vllm_start_begin\":\"$VS0\",\"vllm_start_end\":\"$VS1\"}" > $L.meta.json
$DATA/venv/bin/python $KIT/grade.py $TK "$R" $([ $TK = t6 ] && echo $RM/origin.git) > $L.grade.json 2>> $L.err
echo "$(date +%H:%M) $ID rc=$RC wall=$((END-START))s $(python3 -c "import json;d=json.load(open('$L.grade.json'));print('PASS' if d['pass'] else 'FAIL', d['hidden'], 'traps' if (d.get('traps') or {}).get('any') else '')" 2>/dev/null)"
