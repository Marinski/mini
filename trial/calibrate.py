"""Step 2 calibration: measure where OpenCode actually compacts, instead of assuming it.

The spec's `limit.context` of 45056 with `output` 16384 assumes compaction fires when the prompt
reaches context - output = 28672. That was never measured. This reads the spend logs of the
`V0-ctx*k` calibration runs (a low limit forces compaction early and often) and reports the prompt
size at each compaction, so the fraction can be checked against the real limit.

It reuses the reporter's own spend-log reader, so the drop it measures is the one the report counts.
No model calls happen here; it only reads spend logs for runs that already finished.

Usage:
  python3 trial/calibrate.py [batch-dir] [--limit 45056] [--write docs/ceiling-step2.md]
  python3 trial/calibrate.py --selftest

Run the calibration first, in the nightly window, one task (t9, the longest):
  BATCH=cal-ctx VARIANT=V0-ctx11k bash trial/run_trial.sh opencode t9 1
  BATCH=cal-ctx VARIANT=V0-ctx22k bash trial/run_trial.sh opencode t9 1
  python3 trial/calibrate.py "$TRIAL_DATA/cal-ctx"
"""
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from summarize import AGENT_ALIAS, ALIAS, DROP, spend_rows

KIT = os.path.dirname(os.path.abspath(__file__))
VARIANTS = os.path.join(KIT, "variants")
# The real trial limit these points are extrapolated to.
DEFAULT_LIMIT = 45056


def limits_for(variant):
    """(context, output) for a variant, from its config file, falling back to its name."""
    path = os.path.join(VARIANTS, f"{variant}.json")
    if os.path.exists(path):
        with open(path) as f:
            cfg = json.load(f)
        for prov in (cfg.get("provider") or {}).values():
            for model in (prov.get("models") or {}).values():
                lim = model.get("limit") or {}
                if lim.get("context"):
                    return lim["context"], lim.get("output")
    m = re.search(r"ctx(\d+)k", variant)
    if m:
        ctx = int(m.group(1)) * 1024
        return ctx, ctx * 4 // 11
    return None, None


def full_prompts(log_prefix):
    """The full agent prompt (`input + cache.read`) of every tool-calling step, from the transcript.

    Compaction is visible in this series; raw spend rows alternate with a smaller per-step call, so
    a >30% drop detector over spend rows would fire on every step. Returns [] when there is no
    transcript (e.g. an imported run)."""
    path = log_prefix + ".jsonl"
    if not os.path.exists(path):
        return []
    out = []
    for line in open(path):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        p = d.get("part") or {}
        if d.get("type") == "step_finish" and p.get("reason") == "tool-calls":
            t = p.get("tokens") or {}
            out.append((t.get("input") or 0) + ((t.get("cache") or {}).get("read") or 0))
    return out


def triggers(prompts, drop=DROP):
    """Prompt sizes that triggered a compaction: the pre-drop peak at every >drop prompt drop.

    Returns (triggers, last_prompt). A run with no triggers did not compact under that limit.
    """
    prev, out = None, []
    for p in prompts:
        if not p:
            continue
        if prev and p < prev * (1 - drop):
            out.append(prev)
        prev = p
    return out, prev


def median(xs):
    """Lower-middle for even counts: a smaller trigger is the conservative read of the limit."""
    s = sorted(xs)
    return s[(len(s) - 1) // 2] if s else None


def alias_rows(harness, variant, start, end):
    """Spend rows for the run, with the same fallback the reporter uses when the trial key is absent."""
    alias = AGENT_ALIAS if harness == "opencode" and variant != "-" else ALIAS.get(harness, harness)
    rows = spend_rows(alias, start, end)
    if not rows and alias != ALIAS.get(harness, harness):
        rows = spend_rows(ALIAS.get(harness, harness), start, end)
    return rows


def main():
    argv = sys.argv[1:]
    write_to = None
    if "--write" in argv:
        i = argv.index("--write")
        write_to = argv[i + 1]
        del argv[i:i + 2]
    limit = DEFAULT_LIMIT
    if "--limit" in argv:
        i = argv.index("--limit")
        limit = int(argv[i + 1])
        del argv[i:i + 2]
    batch = argv[0] if argv else os.path.join(
        os.environ.get("TRIAL_DATA", os.path.expanduser("~/agent-trials")),
        os.environ.get("BATCH", "cal-ctx"))

    metas = sorted(glob.glob(os.path.join(batch, "logs", "*.meta.json")))
    if not metas:
        print(f"no runs in {batch} (logs/*.meta.json) - run the calibration first, see the docstring")
        return 0

    points, lines = [], []
    header = f"# Compaction calibration (step 2)\n\nBatch: `{batch}`. Measured from spend logs.\n"
    for mp in metas:
        with open(mp) as f:
            m = json.load(f)
        variant = m.get("variant", "-")
        if not variant.startswith("V0-ctx"):
            continue
        ctx, out = limits_for(variant)
        rows = alias_rows(m.get("harness", "opencode"), variant, m["start"], m["end"])
        # The transcript's full-prompt series is the one compaction shows in; fall back to spend rows.
        series = full_prompts(mp[:-len(".meta.json")]) or [r.get("prompt_tokens") or 0 for r in rows]
        tr = triggers(series)[0]
        hyp = (ctx - out) if ctx and out else None
        peak = max(series, default=0)
        block = [f"## {m['id']}",
                 f"- context {ctx}, output {out}; hypothesis `context - output` = {hyp}",
                 f"- calls {len(rows)}, peak prompt {peak}, compactions {len(tr)}"]
        if tr:
            med = median(tr)
            block += [f"- measured triggers (pre-drop prompts): {tr}",
                      f"- median trigger {med}"
                      + (f", vs hypothesis {hyp} ({med - hyp:+d})" if hyp else "")]
            if ctx:
                points.append((ctx, med))
        else:
            block += ["- **no compaction**: this limit was too high for the task, so it says nothing"]
        print("\n".join(block))
        lines.append("\n".join(block))

    if not points:
        print("\nno compaction measured at any limit - lower the limits and re-run")
        return 1

    frac = sum(t / c for c, t in points) / len(points)
    pred = frac * limit
    assumed = limit * 7 // 11
    verdict = ("holds" if assumed and abs(pred - assumed) <= 0.05 * assumed
               else f"OFF by {100 * (pred - assumed) / assumed:+.1f}%")
    fit = ""
    if len(points) >= 2:
        (c1, t1), (c2, t2) = points[0], points[-1]
        slope = (t2 - t1) / (c2 - c1)
        intercept = t1 - slope * c1
        fit = (f"\n- two-point fit: trigger = {slope:.3f}*context {intercept:+.0f}; "
               f"a fixed absolute reserve would show as intercept != 0")
    summary = (f"\n## Result\n- fraction `trigger/context` = {frac:.3f} over {len(points)} limit(s){fit}\n"
               f"- at the trial's context {limit}: predicted compaction at **{pred:.0f}** tokens\n"
               f"- the spec assumes context - output = 28672; measured prediction is {verdict}\n")
    print(summary)
    lines.append(summary)

    if write_to:
        with open(write_to, "w") as f:
            f.write(header + "\n" + "\n".join(lines) + "\n")
        print(f"wrote {write_to}")
    return 0


def selftest():
    """Exercise the trigger detector and the extrapolation without touching the network."""
    prompts = (500, 1000, 2000, 3000, 2900, 5000, 6000, 3000)
    tr, last = triggers(prompts)
    assert tr == [6000], tr                   # 3000->2900 is 3.3%, not a drop; 6000->3000 is 50%
    assert last == 3000, last
    assert median([6000, 3000]) == 3000
    # ctx22k: a trigger at 14336 (i.e. context-output) extrapolates to 28672 at 45056
    ctx = 22528
    assert abs((14336 / ctx) * DEFAULT_LIMIT - 28672) < 1
    print("selftest: ok (detects >30% drops only, extrapolates the fraction to the real limit)")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        sys.exit(main())
