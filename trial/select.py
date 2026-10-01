"""Pick which variants go on from a finished batch, per SPEC-context-plugins.md.

    python3 trial/select.py --pilot  <batch>   # survivors after the pilot's drop rule (step 7)
    python3 trial/select.py --finalists <batch>  # Stage B finalists (step 8)
    python3 trial/select.py --selftest

Prints one variant name per line on stdout, so a queue can use it:
    VARIANTS="V0 $(python3 trial/select.py --pilot ctx-pilot)" BATCH=ctx-a queue.sh opencode 3 "t2 t8 t9"

Reads <batch>/results.json (rows written by summarize.py).
"""
import json
import os
import statistics
import sys

KIT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KIT)
from summarize import DATA, SAVE_WALL, SAVE_TOK, CACHE_SLACK, TASKS  # noqa: E402


def load(batch):
    path = batch if os.path.exists(batch) else os.path.join(DATA, batch, "results.json")
    with open(path) as f:
        return json.load(f)


def med(rs, k):
    v = [r[k] for r in rs if isinstance(r.get(k), (int, float))]
    return statistics.median(v) if v else None


def pooled(rs):
    c = sum(r["cache_abs"] for r in rs if r.get("cache_abs") is not None)
    d = sum(r["cache_den"] for r in rs if r.get("cache_den") is not None)
    return 100.0 * c / d if d else None


def variants(rows):
    return sorted({r["variant"] for r in rows if r["variant"] not in ("-", "V0")})


def drop_reasons(rows, v, base="V0"):
    """The pilot's three drop conditions (step 7): lost 2 of 3 tasks V0 passed; >=1.5x V0 wall on
    2 of 3 tasks; cache hit % collapsed (below V0 by more than the decision rule's slack)."""
    vr = [r for r in rows if r["variant"] == v]
    br = [r for r in rows if r["variant"] == base]
    lost = []
    for t in TASKS:
        b = [r for r in br if r["task"] == t and r["pass"]]
        a = [r for r in vr if r["task"] == t]
        if b and not any(r["pass"] for r in a):
            lost.append(t)
    slow = []
    for t in TASKS:
        a, b = [r for r in vr if r["task"] == t], [r for r in br if r["task"] == t]
        ma, mb = med(a, "wall_min"), med(b, "wall_min")
        if ma and mb and ma / mb >= 1.5:
            slow.append(t)
    c, bc = pooled(vr), pooled(br)
    reasons = []
    if len(lost) >= 2:
        reasons.append(f"no pass on {len(lost)}/3 tasks V0 passed ({','.join(lost)})")
    if len(slow) >= 2:
        reasons.append(f">=1.5x V0 wall on {len(slow)}/3 tasks ({','.join(slow)})")
    if c is not None and bc is not None and c < bc - CACHE_SLACK:
        reasons.append(f"cache {c:.1f}% vs V0 {bc:.1f}% ({round(bc - c)} pts)")
    return reasons


def pilot(rows, base="V0"):
    keep, dropped = [], []
    for v in variants(rows):
        rs = drop_reasons(rows, v, base)
        if rs:
            dropped.append((v, rs))
        else:
            keep.append(v)
    for v, rs in dropped:
        print(f"select: drop {v}: {'; '.join(rs)}", file=sys.stderr)
    for v in keep:
        print(f"select: keep {v}", file=sys.stderr)
    return keep


def finalists(rows, base="V0"):
    """Stage A -> Stage B: a variant that already passes the decision rule, or is within 0.10 of
    the 0.80 ratio on wall time or tokens (its VERDICT may still be no on passes or cache)."""
    from summarize import decide
    out = []
    for d in decide(rows, base):
        near = min([x for x in (d["wall_ratio"], d["tok_ratio"]) if x is not None], default=None)
        if d["verdict"] == "YES" or (near is not None and near <= SAVE_WALL + 0.10):
            out.append(d["variant"])
    return out


def selftest():
    def run(v, t, ok, wall, tin, cache):
        return {"variant": v, "harness": "opencode", "task": t, "pass": ok, "timed_out": False,
                "wall_min": wall, "tok_in": tin, "tok_in_total": tin, "cache_pct": cache,
                "cache_abs": round(tin * cache / 100), "cache_den": tin}
    bad = []
    # V1 wins (fast, same passes, same cache): kept. V2 loses 2 tasks V0 passed: dropped.
    rows = ([run("V0", t, True, 10, 100000, 50) for t in TASKS] +
            [run("V1", t, True, 6, 60000, 50) for t in TASKS] +
            [run("V2", t, t != "t2" and t != "t6", 6, 60000, 50) for t in TASKS] +
            [run("V3", t, True, 10, 100000, 30) for t in TASKS])   # cache 20 down: dropped
    kept = pilot(rows)
    if sorted(kept) != ["V1"]:
        bad.append(f"pilot kept {kept}, want [V1]")
    fin = finalists([run("V0", t, True, 10, 100000, 50) for t in TASKS] +
                    [run("V1", t, True, 8.5, 100000, 50) for t in TASKS])  # ratio 0.85: within 0.10
    if fin != ["V1"]:
        bad.append(f"finalists {fin}, want [V1]")
    print("select selftest:", "FAILED\n  " + "\n  ".join(bad) if bad else
          "ok (pilot drops lost/slow/cache-collapsed; finalists take the 0.10 band)")
    return not bad


def main(argv):
    if "--selftest" in argv:
        return 0 if selftest() else 1
    if "--pilot" in argv:
        print("\n".join(pilot(load(argv[argv.index('--pilot') + 1]))))
        return 0
    if "--finalists" in argv:
        print("\n".join(finalists(load(argv[argv.index('--finalists') + 1]))))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
