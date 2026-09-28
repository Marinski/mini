"""mini-harness: a 4-tool coding agent on aigate LiteLLM (chat completions).

bash / read / edit / write, one loop, output clipping, a step limit and a time budget.
Runs in a container whose only mounted folder is WORK; the transcript goes to LOG.
"""
import json, os, subprocess, sys, time
from pathlib import Path
from openai import OpenAI

WORK = Path(os.environ.get("WORK", "/work")).resolve()
LOG = os.environ.get("LOG", "/out/transcript.jsonl")
client = OpenAI(base_url=os.environ.get("BASE_URL", "http://172.17.0.1:4000/v1"),
                api_key=os.environ["LITELLM_KEY"], timeout=1800, max_retries=2)
MODEL = os.environ.get("MODEL", "vllm-qwen3.8-nothink")
MAX_STEPS, BUDGET_S, MAX_OUT = 60, 2640, 20_000

SYSTEM = f"""You are a coding agent working in {WORK}. Use the tools to inspect and change files,
run tests with bash, and reply without a tool call when the task is done. Make minimal edits."""

def fn(name, desc, props, req):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": req}}}

S = {"type": "string"}
TOOLS = [
    fn("bash", "Run a shell command in the work folder.", {"command": S}, ["command"]),
    fn("read", "Read a text file with line numbers.", {"path": S, "offset": {"type": "integer"}, "limit": {"type": "integer"}}, ["path"]),
    fn("edit", "Replace one exact, unique snippet in a file.", {"path": S, "old": S, "new": S}, ["path", "old", "new"]),
    fn("write", "Create or overwrite a whole file.", {"path": S, "content": S}, ["path", "content"]),
]

def inside(p):
    path = (WORK / p).resolve()
    if path != WORK and WORK not in path.parents:
        raise ValueError(f"{p} is outside the work folder")
    return path

def clip(text):
    return text if len(text) <= MAX_OUT else text[:MAX_OUT // 2] + "\n...[cut]...\n" + text[-MAX_OUT // 2:]

def run_tool(name, a):
    if name == "bash":
        r = subprocess.run(a["command"], shell=True, cwd=WORK, capture_output=True, text=True, timeout=300)
        return clip(f"exit {r.returncode}\n{r.stdout}{r.stderr}")
    if name == "read":
        lines = inside(a["path"]).read_text().splitlines()
        start = int(a.get("offset") or 1); end = start - 1 + int(a.get("limit") or 400)
        return clip("\n".join(f"{i}\t{l}" for i, l in enumerate(lines[start - 1:end], start)))
    if name == "edit":
        p = inside(a["path"]); text = p.read_text(); n = text.count(a["old"])
        if n != 1:
            return f"error: 'old' found {n} times in {a['path']}; it must match exactly once. Read the file and retry."
        p.write_text(text.replace(a["old"], a["new"])); return "ok"
    if name == "write":
        p = inside(a["path"]); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(a["content"]); return "ok"
    return f"error: unknown tool {name}"

def main(task):
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": task}]
    log, t0 = open(LOG, "a"), time.time()
    for step in range(MAX_STEPS):
        if time.time() - t0 > BUDGET_S:
            print("stopped: time budget"); return
        msg = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS,
                                             temperature=0.7, max_tokens=8000).choices[0].message
        turn = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            turn["tool_calls"] = [{"id": c.id, "type": "function",
                                   "function": {"name": c.function.name, "arguments": c.function.arguments}}
                                  for c in msg.tool_calls]
        messages.append(turn)
        log.write(json.dumps({"step": step, "t": round(time.time() - t0, 1), "content": (msg.content or "")[:2000],
                              "calls": [c.function.name for c in msg.tool_calls or []]}) + "\n"); log.flush()
        if not msg.tool_calls:
            print(msg.content); return
        for call in msg.tool_calls:
            try:
                result = run_tool(call.function.name, json.loads(call.function.arguments or "{}"))
            except Exception as e:
                result = f"error: {e}"
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
            log.write(json.dumps({"step": step, "tool": call.function.name, "result": result[:2000]}) + "\n"); log.flush()
    print("stopped: step limit")

if __name__ == "__main__":
    main(sys.argv[1])
