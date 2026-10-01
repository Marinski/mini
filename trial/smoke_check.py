"""Step 6 plugin smoke evidence: what each variant's faithful run left behind.

Reads `$TRIAL_DATA/smoke` and prints one row per variant. It can only assert what the logs and state
carry; where a proof needs the request body (LiteLLM does not store bodies here), the row says so
instead of guessing. Run:  python3 trial/smoke_check.py
"""
import glob
import json
import os
import sys

KIT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KIT)
from summarize import DATA, AGENT_ALIAS, spend_rows, transcript_stats  # noqa: E402

SMOKE = os.path.join(DATA, "smoke")


def state_evidence(st):
    ctx = os.path.isdir(os.path.join(st, "data", "magic-context"))
    mc = os.path.exists(os.path.join(st, "data", "magic-context", "context.db"))
    am = os.path.isdir(os.path.join(st, "data", "agentmemory")) and bool(
        os.listdir(os.path.join(st, "data", "agentmemory"))) if os.path.isdir(os.path.join(st, "data", "agentmemory")) else False
    return mc, am


def main():
    rows = []
    for mp in sorted(glob.glob(os.path.join(SMOKE, "logs", "*.meta.json"))):
        m = json.load(open(mp))
        p = mp[:-len(".meta.json")]
        v = m.get("variant", "?")
        tr = transcript_stats(p + ".jsonl") or {}
        tools = tr.get("tools") or {}
        ctx_calls = sum(n for name, n in tools.items() if name.startswith("ctx_"))
        # Prefer the runner's own plugin-evidence line, which the memory server and plugins write.
        ev = ""
        try:
            ev = " ".join(l for l in open(p + ".err", errors="ignore") if "plugin-evidence" in l)
        except OSError:
            pass
        st = os.path.join(SMOKE, "state", m.get("id", ""))
        mc_db, am_data = state_evidence(st)
        hist = len(spend_rows("trial-historian", m["start"], m["end"]))
        s2 = os.path.exists(p + ".s2.jsonl")
        rows.append((v, m["id"], ctx_calls, "ctx_sessions" in ev, mc_db, am_data, hist,
                     tr.get("steps"), "s2" if s2 else "-"))
    print("| Variant | run | ctx_ tool calls | ctx_sessions | magic-context db | agentmemory data | historian calls | steps | session2 |")
    print("|---|---|---|---|---|---|---|---|---|")
    for v, i, cc, cs, mc, am, h, st, s2 in rows:
        print(f"| {v} | {i} | {cc} | {'yes' if cs else '-'} | {'yes' if mc else '-'} | "
              f"{'yes' if am else '-'} | {h} | {st} | {s2} |")
    print()
    print("Notes: V1's instruction text is wired in the config and mounted (trial/cheap-reads.md); "
          "its runtime proof needs the request body, which LiteLLM does not retain here. V4's memory "
          "injection likewise needs the body; the `agentmemory data` column is its capture proof, and "
          "`session2` shows the H run reached session 2.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
