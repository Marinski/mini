"""Step 0: the offline ceiling for ContextMode - how much of a session's tool output it could index.

ContextMode indexes large tool outputs and hands the model a pointer instead of the text, so the
only thing that can pay for itself is the share of tool-output bytes living in outputs over a
threshold. This measures that share from transcripts that already exist, with no model calls:

    python ceiling.py --transcripts '~/agent-trials/*/logs/opencode*.jsonl'   # the trial's own runs
    python ceiling.py --store ~/.local/share/opencode/opencode.db --top 10     # real host sessions
    python ceiling.py --transcripts ... --store ... --out docs/ceiling.md      # both, written out

Sources are OpenCode's own record of what the model was shown: the JSONL transcripts from
run_trial.sh (`tool_use.part.state.output`) and the host store's `part` table, same shape.
"""
import argparse
import collections
import glob as globmod
import json
import os
import sqlite3
import statistics
import sys


def tool_outputs_from_jsonl(path):
    """Yield (tool, output_bytes) for every completed tool call in an opencode JSONL transcript."""
    for line in open(path, errors="replace"):
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") != "tool_use":
            continue
        state = (event.get("part") or {}).get("state") or {}
        if state.get("status") not in (None, "completed"):
            continue  # a failed call's error text is not what the model was shown either, but keep it simple
        out = state.get("output")
        if not isinstance(out, str):
            continue
        yield event["part"].get("tool") or "?", len(out.encode())


def tool_outputs_from_store(db, session_id):
    """Same, for one session in OpenCode's SQLite store (read-only)."""
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = con.execute("select data from part where session_id=?", (session_id,))
    for (data,) in rows:
        try:
            part = json.loads(data)
        except ValueError:
            continue
        if part.get("type") != "tool":
            continue
        out = (part.get("state") or {}).get("output")
        if isinstance(out, str):
            yield part.get("tool") or "?", len(out.encode())


def top_store_sessions(db, top):
    """The `top` sessions with the most prompt tokens in: the 'long real sessions' step 0 asks for."""
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = con.execute("""select id, title, tokens_input, tokens_cache_read, cost, time_created
                          from session where parent_id is null order by tokens_input desc limit ?""", (top,)).fetchall()
    con.close()
    return [dict(zip(("id", "title", "tokens_in", "cache_read", "cost", "created"), r)) for r in rows]


def measure(label, outputs, min_bytes):
    """One row: total tool-output bytes, how much of it is over the threshold, and that share."""
    per_tool = collections.Counter()
    total = big = calls = 0
    for tool, n in outputs:
        per_tool[tool] += n
        calls += 1
        total += n
        if n > min_bytes:
            big += n
    return {"label": label, "calls": calls, "total_bytes": total, "big_bytes": big,
            "share": big / total if total else 0.0, "by_tool": per_tool}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--transcripts", help="glob of opencode JSONL transcripts (run_trial.sh output)")
    ap.add_argument("--store", help="path to OpenCode's opencode.db, for real host sessions")
    ap.add_argument("--top", type=int, default=10, help="host sessions to include (default 10)")
    ap.add_argument("--min-bytes", type=int, default=5000, help="ContextMode's index threshold (default 5000)")
    ap.add_argument("--out", help="write the markdown table here as well as to stdout")
    args = ap.parse_args()

    rows = []
    for pattern in filter(None, (args.transcripts,)):
        for path in sorted(globmod.glob(os.path.expanduser(pattern))):
            batch, task = os.path.basename(os.path.dirname(os.path.dirname(path))), os.path.basename(path).split("-")[1]
            rows.append({**measure(f"{batch} / {os.path.basename(path)}", tool_outputs_from_jsonl(path), args.min_bytes),
                         "kind": "trial", "task": task})
    if args.store:
        db = os.path.expanduser(args.store)
        for s in top_store_sessions(db, args.top):
            rows.append({**measure(s["title"] or s["id"], tool_outputs_from_store(db, s["id"]), args.min_bytes),
                         "kind": "host", "task": "-", "session": s})

    if not rows:
        sys.exit("ceiling: no transcripts or store sessions found")

    trial = [r for r in rows if r["kind"] == "trial"]
    host = [r for r in rows if r["kind"] == "host"]
    L = [f"# ContextMode offline ceiling (step 0)", "",
         f"Share of tool-output bytes in outputs over {args.min_bytes:,} bytes - what ContextMode would index.", "",
         "| Source | Task | Tool calls | Tool output | Indexed-able | Share |", "|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['label']} | {r['task']} | {r['calls']} | {r['total_bytes']/1e6:.2f} MB | "
                 f"{r['big_bytes']/1e6:.2f} MB | **{r['share']*100:.1f}%** |")

    def agg(group, name):
        if not group:
            return
        pooled = sum(r["big_bytes"] for r in group) / sum(r["total_bytes"] for r in group)
        L.append("")
        L.append(f"| **{name} pooled** | - | {sum(r['calls'] for r in group)} | "
                 f"{sum(r['total_bytes'] for r in group)/1e6:.2f} MB | {sum(r['big_bytes'] for r in group)/1e6:.2f} MB | "
                 f"**{pooled*100:.1f}%** |")
        L.append(f"| **{name} median per session** | - | - | - | - | "
                 f"**{statistics.median(r['share'] for r in group)*100:.1f}%** |")

    agg(trial, "Trial transcripts")
    agg(host, "Real host sessions")
    for task in sorted({r["task"] for r in trial}):
        agg([r for r in trial if r["task"] == task], f"Trial {task} only")

    biggest = collections.Counter()
    for r in host:
        biggest.update(r["by_tool"])
    if biggest:
        L += ["", "## Which tools produce the indexable bytes (real host sessions)", "", "| Tool | Bytes | Share |", "|---|---|---|"]
        for tool, n in biggest.most_common(8):
            L.append(f"| {tool} | {n/1e6:.2f} MB | {n/sum(biggest.values())*100:.1f}% |")

    rep = "\n".join(L) + "\n"
    if args.out:
        os.makedirs(os.path.dirname(os.path.expanduser(args.out)), exist_ok=True)
        open(args.out, "w").write(rep)
    print(rep)


if __name__ == "__main__":
    main()