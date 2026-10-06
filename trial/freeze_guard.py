"""Stop a trial run when the model freezes (MODEL_LABEL / QWEN_METRICS_URL env): python freeze_guard.py <run-pid> <log-prefix> [pibox-workspace]

Every 30 s it reads Qwen's vLLM /metrics. If requests are running or waiting and
no new tokens appear for 2 minutes, it kills the run (the whole process tree
under <run-pid>, plus the agent inside pibox for that workspace), writes
<log-prefix>.freeze.json and ../FROZEN (run_trial.sh refuses to start while
FROZEN exists; delete it after the head restarts Qwen) and posts to Discord.

KV cache usage counts as progress too: during a long chunked prefill the
token counters stay flat but KV usage grows with every chunk.

Every sample is also appended to <log-prefix>.samples.jsonl (time, running,
waiting, prompt/generation tokens), so the report can mark a run that overlapped
other Qwen traffic: the trial runs alone, so requests beyond the agent's own are
someone else's.
"""
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request

METRICS = os.environ.get("QWEN_METRICS_URL", "http://localhost:8001/metrics")
POLL = float(os.environ.get("FREEZE_POLL_SECONDS", 30))
STALL = float(os.environ.get("FREEZE_STALL_SECONDS", 120))
PROGRESS = ("vllm:generation_tokens_total", "vllm:prompt_tokens_total", "vllm:kv_cache_usage_perc")
QUEUE = ("vllm:num_requests_running", "vllm:num_requests_waiting")
# SGLang's /metrics names for the same counters, read into the vLLM keys (SGLang trial, Oct 2026).
SGLANG = {"sglang:generation_tokens_total": "vllm:generation_tokens_total",
          "sglang:prompt_tokens_total": "vllm:prompt_tokens_total",
          "sglang:token_usage": "vllm:kv_cache_usage_perc",
          "sglang:num_running_reqs": "vllm:num_requests_running",
          "sglang:num_queue_reqs": "vllm:num_requests_waiting"}
LABEL = os.environ.get("MODEL_LABEL", "Qwen")
AGENTPIPE_ENV = os.path.expanduser(os.environ.get("NOTIFY_ENV_FILE", "~/repos/agentpipe/.env"))


def read_metrics():
    values = dict.fromkeys(PROGRESS + QUEUE, 0.0)
    for line in urllib.request.urlopen(METRICS, timeout=10).read().decode().splitlines():
        name = line.split("{", 1)[0].split(" ", 1)[0]
        name = SGLANG.get(name, name)
        if name in values:
            values[name] += float(line.rsplit(" ", 1)[1])
    return values


def descendants(pid):
    children = {}
    for entry in os.listdir("/proc"):
        if entry.isdigit():
            try:
                ppid = int(open(f"/proc/{entry}/stat").read().rsplit(")", 1)[1].split()[1])
            except (OSError, IndexError, ValueError):
                continue
            children.setdefault(ppid, []).append(int(entry))
    found, todo = [], [pid]
    while todo:
        p = todo.pop()
        found.append(p)
        todo += children.get(p, [])
    return found


def kill_tree(pid):
    tree = descendants(pid)  # listed before killing: orphans get reparented
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for p in reversed(tree):
            try:
                os.kill(p, sig)
            except ProcessLookupError:
                pass
        for _ in range(10):
            if not any(os.path.exists(f"/proc/{p}") for p in tree):
                return
            time.sleep(1)


def stop_pibox_agent(workspace):
    # only processes whose working directory is this trial's workspace
    script = ("for p in /proc/[0-9]*; do [ \"$(readlink $p/cwd)\" = /workspace/%s ] && kill -9 ${p#/proc/}; done; true" % workspace)
    subprocess.run(["docker", "exec", "aigate-pibox-1", "sh", "-c", script], timeout=30, check=False)


def notify(text):
    env = {}
    try:
        for line in open(AGENTPIPE_ENV):
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.strip().split("=", 1)
                env[k] = v.strip().strip("\"").strip("'")
    except OSError:
        return
    token, channel = env.get("AGENTPIPE_DISCORD_TOKEN"), env.get("AGENTPIPE_DISCORD_CHANNEL_ID")
    if not (token and channel):
        return
    request = urllib.request.Request(
        f"https://discord.com/api/v10/channels/{channel}/messages",
        data=json.dumps({"content": text[:1900]}).encode(),
        headers={"Authorization": f"Bot {token}", "Content-Type": "application/json", "User-Agent": "trial-freeze-guard"})
    try:
        urllib.request.urlopen(request, timeout=15).read()
    except Exception as e:
        print(f"discord notify failed: {e}", file=sys.stderr)


def main(pid, prefix, workspace=None):
    fingerprint, since = None, time.time()
    open(prefix + ".samples.jsonl", "w").close()   # fresh per run; the report reads this
    while os.path.exists(f"/proc/{pid}"):
        try:
            m = read_metrics()
        except Exception as e:
            print(f"freeze_guard: /metrics failed: {e}", file=sys.stderr)
            time.sleep(POLL)
            continue
        now = time.time()
        with open(prefix + ".samples.jsonl", "a") as fh:
            fh.write(json.dumps({"t": round(now), "running": m["vllm:num_requests_running"],
                                 "waiting": m["vllm:num_requests_waiting"],
                                 "prompt": m["vllm:prompt_tokens_total"],
                                 "generation": m["vllm:generation_tokens_total"]}) + "\n")
        current = [m[k] for k in PROGRESS]
        busy = m["vllm:num_requests_running"] + m["vllm:num_requests_waiting"] > 0
        if current != fingerprint or not busy:
            fingerprint, since = current, now
        elif now - since >= STALL:
            run = os.path.basename(prefix)
            info = {"run": run, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
                    "stalled_s": round(now - since), **m}
            json.dump(info, open(prefix + ".freeze.json", "w"), indent=1)
            open(os.path.join(os.path.dirname(os.path.dirname(prefix)), "FROZEN"), "w").write(json.dumps(info) + "\n")
            kill_tree(pid)
            if workspace:
                stop_pibox_agent(workspace)
            text = (f"**Trial stopped: {LABEL} froze** during `{run}`: "
                    f"{int(m['vllm:num_requests_running'])} running, no new tokens for {round(now - since)} s "
                    f"(generation_tokens_total {int(m['vllm:generation_tokens_total'])}). "
                    f"On the head: save `docker logs` and restart the {LABEL} vLLM container, then delete the batch's FROZEN file.")
            print(text, file=sys.stderr)
            notify(text)
            return 3
        time.sleep(POLL)
    return 0


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1]), sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None))
