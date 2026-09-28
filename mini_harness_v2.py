"""mini-harness v2: a 4-tool coding agent on aigate LiteLLM (chat completions).

v1 plus pi-style tool behaviour (README.md): multi-edit with a diff, paged reads, output cut
at line boundaries, tool guidance in the prompt, longer transport retries, and a logged stop
cause and prompt size. Runs in a container whose only mounted folder is WORK; the transcript
goes to LOG.
"""
import difflib
import json
import os
import subprocess
import sys
import time
from itertools import pairwise
from pathlib import Path

import openai
from openai import OpenAI

WORK = Path(os.environ.get("WORK", "/work")).resolve()
LOG = os.environ.get("LOG", "/out/transcript.jsonl")
MODEL = os.environ.get("MODEL", "vllm-qwen3.8-nothink")
MAX_STEPS, BUDGET_S, MAX_OUT = 60, 2640, 20_000
READ_LINES, HEAD_LINES, DIFF_MAX = 2000, 50, 1500

SYSTEM = f"""You are a coding agent working in {WORK}. You help by reading files, running \
commands, editing code and writing new files.

Tools:
- bash: run a shell command in the work folder (ls, rg, find, tests). Long output keeps its \
first 50 lines and its end.
- read: read a file with line numbers, up to 2000 lines per call; a note says where to continue.
- edit: exact text replacement in one file; several places per call via edits[].
- write: create a new file or replace a whole file.

Guidelines:
- Explore with bash (ls, rg, find) before changing code, and read a file before editing it.
- Put all changes to one file in one edit call. Keep each edits[].old as small as possible \
while still matching exactly once in the original file; do not let edits overlap.
- Use write only for new files or complete rewrites.
- Make minimal changes that do what the task asks, and nothing else.
- Run the project's tests before you finish, then reply without a tool call."""


def fn(name, desc, props, req):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": req}}}


S = {"type": "string"}
EDIT = {"type": "object", "properties": {"old": S, "new": S}, "required": ["old", "new"]}
TOOLS = [
    fn("bash", "Run a shell command in the work folder.", {"command": S}, ["command"]),
    fn("read", "Read a text file with line numbers, up to 2000 lines per call.",
       {"path": S, "offset": {"type": "integer"}, "limit": {"type": "integer"}}, ["path"]),
    fn("edit", "Replace exact text in one file. Each edits[].old must match exactly once in the "
       "original file; edits must not overlap.",
       {"path": S, "edits": {"type": "array", "items": EDIT}}, ["path", "edits"]),
    fn("write", "Create or overwrite a whole file.", {"path": S, "content": S}, ["path", "content"]),
]


def inside(p, work):
    path = (work / p).resolve()
    if path != work and work not in path.parents:
        raise ValueError(f"{p} is outside the work folder")
    return path


def cut_lines(text):
    """Fit text in MAX_OUT: up to HEAD_LINES whole lines (a quarter of the room at most), a note,
    then as many whole last lines as fit. A line longer than the head's room keeps its start in
    the head; a last line too long for the tail keeps its end. Both are marked with "…"."""
    if len(text) <= MAX_OUT:
        return text
    lines = text.splitlines()
    head, size = [], 0
    for line in lines[:HEAD_LINES]:
        if size + len(line) + 1 > MAX_OUT // 4:
            if len(line) > MAX_OUT // 4:
                head.append(line[:MAX_OUT // 4 - size] + "…")
                size = MAX_OUT // 4 + 2
            break
        head.append(line)
        size += len(line) + 1
    room = MAX_OUT - size - 40
    tail = []
    for line in reversed(lines[len(head):]):
        if len(line) + 1 > room:
            break
        tail.append(line)
        room -= len(line) + 1
    tail.reverse()
    if not tail:
        tail = ["…" + lines[-1][-max(room - 1, 1):]]
    skipped = max(len(lines) - len(head) - len(tail), 0)
    note = f"...[cut {skipped} lines]..." if skipped else "...[cut inside a long line]..."
    return "\n".join([*head, note, *tail])


def read(a, work):
    lines = inside(a["path"], work).read_text().splitlines()
    start = max(int(a.get("offset") or 1), 1)
    if lines and start > len(lines):
        return f"error: offset {start} is past the end of {a['path']} ({len(lines)} lines)"
    limit = min(max(int(a.get("limit") or READ_LINES), 1), READ_LINES)
    end = min(start - 1 + limit, len(lines))
    rows, size = [], 0
    for i in range(start, end + 1):
        row = f"{i}\t{lines[i - 1]}"
        if len(row) > MAX_OUT:
            row = row[:MAX_OUT] + f" …[line cut: {len(lines[i - 1])} chars; use bash to see all]"
        if rows and size + len(row) + 1 > MAX_OUT:
            end = i - 1
            break
        rows.append(row)
        size += len(row) + 1
    if end < len(lines):
        rows.append(f"[more: {len(lines) - end} lines left; continue with offset={end + 1}]")
    return "\n".join(rows)


def edit(a, work):
    edits = a.get("edits")
    if isinstance(edits, str):
        edits = json.loads(edits)
    if isinstance(edits, dict):
        edits = [edits]
    if edits is None and "old" in a:
        edits = [{"old": a["old"], "new": a.get("new")}]
    if not edits:
        return "error: edits must hold at least one {old, new} pair."
    p = inside(a["path"], work)
    text = p.read_text()
    spans = []
    for i, e in enumerate(edits, 1):
        if not (isinstance(e, dict) and isinstance(e.get("old"), str) and isinstance(e.get("new"), str)):
            return f"error: edit {i} needs 'old' and 'new' strings. Nothing was changed."
        if not e["old"]:
            return f"error: edit {i}: 'old' is empty. Nothing was changed."
        n = text.count(e["old"])
        if n != 1:
            return (f"error: edit {i}: 'old' found {n} times in {a['path']}; it must match exactly "
                    "once. Nothing was changed. Read the file and retry.")
        start = text.index(e["old"])
        spans.append((start, start + len(e["old"]), e["new"], i))
    spans.sort()
    for (_, end1, _, i1), (start2, _, _, i2) in pairwise(spans):
        if start2 < end1:
            return f"error: edits {i1} and {i2} overlap; merge them into one. Nothing was changed."
    new = text
    for start, end, repl, _ in reversed(spans):
        new = new[:start] + repl + new[end:]
    p.write_text(new)
    diff = "".join(line if line.endswith("\n") else line + "\n"  # a last line without newline
                   for line in difflib.unified_diff(text.splitlines(True), new.splitlines(True),
                                                    a["path"], a["path"], n=3))
    return "ok\n" + (diff if len(diff) <= DIFF_MAX else diff[:DIFF_MAX] + "\n...[diff cut]")


def run_tool(name, a, work=None):
    work = work or WORK
    if name == "bash":
        # The agent's shell: it runs in a container that only mounts its work folder.
        r = subprocess.run(a["command"], shell=True, cwd=work, capture_output=True, text=True,  # noqa: S602
                           timeout=300)
        return cut_lines(f"exit {r.returncode}\n{r.stdout}{r.stderr}")
    if name == "read":
        return read(a, work)
    if name == "edit":
        return edit(a, work)
    if name == "write":
        p = inside(a["path"], work)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(a["content"])
        return "ok"
    return f"error: unknown tool {name}"


def main(task):
    client = OpenAI(base_url=os.environ.get("BASE_URL", "http://172.17.0.1:4000/v1"),
                    api_key=os.environ["LITELLM_KEY"], timeout=1800, max_retries=6)
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": task}]
    with Path(LOG).open("a") as log:
        return loop(client, messages, log)


def loop(client, messages, log):
    t0 = time.time()
    for step in range(MAX_STEPS):
        if time.time() - t0 > BUDGET_S:
            print("stopped: time budget")
            return 0
        try:
            resp = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS,
                                                  temperature=0.7, max_tokens=8000)
        except openai.APIError as e:
            cause = f"api error: {type(e).__name__}: {e}"[:500]
            log.write(json.dumps({"step": step, "t": round(time.time() - t0, 1), "stopped": cause}) + "\n")
            log.flush()
            print(f"stopped: {cause}")
            return 1
        msg = resp.choices[0].message
        turn = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            turn["tool_calls"] = [{"id": c.id, "type": "function",
                                   "function": {"name": c.function.name, "arguments": c.function.arguments}}
                                  for c in msg.tool_calls]
        messages.append(turn)
        usage = getattr(resp, "usage", None)
        log.write(json.dumps({"step": step, "t": round(time.time() - t0, 1), "content": (msg.content or "")[:2000],
                              "calls": [c.function.name for c in msg.tool_calls or []],
                              "prompt_tokens": getattr(usage, "prompt_tokens", None)}) + "\n")
        log.flush()
        if not msg.tool_calls:
            print(msg.content)
            return 0
        for call in msg.tool_calls:
            try:
                result = run_tool(call.function.name, json.loads(call.function.arguments or "{}"))
            except Exception as e:  # noqa: BLE001  (any tool failure goes back to the model)
                result = f"error: {e}"
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
            log.write(json.dumps({"step": step, "tool": call.function.name, "result": result[:2000]}) + "\n")
            log.flush()
    print("stopped: step limit")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
