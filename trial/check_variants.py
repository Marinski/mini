#!/usr/bin/env python3
"""Print each variant's merged OpenCode config and what it adds to V0.

The step 3 check in SPEC-context-plugins.md: a diff against V0 must show only the rows the spec
allows, so an accidental edit (a stray key, a lost instruction, compaction left on in a Magic Context
variant) shows up before a run rather than after one.

    python3 trial/check_variants.py            # every variant, differences only
    python3 trial/check_variants.py V3 V6      # just these
"""

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent
VARIANTS = ROOT / "variants"

# provider -> which LiteLLM key alias the config's {env:...} placeholder resolves to.
KEY_ENV = {"AIGATE_KEY": "trial-opencode", "AIGATE_HISTORIAN_KEY": "trial-historian"}


def flat(prefix, obj, out):
    if isinstance(obj, dict):
        for k, v in obj.items():
            flat(f"{prefix}.{k}" if prefix else k, v, out)
    else:
        out[prefix] = obj


def diff(base, cfg):
    """Keys the variant adds or changes relative to V0 (nothing is ever removed)."""
    b, c = {}, {}
    flat("", base, b)
    flat("", cfg, c)
    out = []
    for k in sorted(c):
        if k not in b:
            out.append(f"+ {k} = {json.dumps(c[k])}")
        elif b[k] != c[k]:
            out.append(f"~ {k}: {json.dumps(b[k])} -> {json.dumps(c[k])}")
    for k in sorted(set(b) - set(c)):
        out.append(f"- {k} (missing)")
    return out


def main(argv):
    names = argv[1:] or sorted(p.stem for p in VARIANTS.glob("V?.json"))
    cfgs = {}
    for n in names:
        p = VARIANTS / f"{n}.json"
        if not p.exists():
            print(f"{n}: MISSING {p}", file=sys.stderr)
            return 1
        cfgs[n] = json.loads(p.read_text())
    if "V0" not in cfgs:
        print("V0 is the baseline and must be among the variants", file=sys.stderr)
        return 1

    v0 = cfgs["V0"]
    print(f"V0 baseline: model={v0.get('model')} context={v0['provider']['aigate']['models'][next(iter(v0['provider']['aigate']['models']))]['limit']['context']}"
          f" plugins={v0.get('plugin', [])} compaction={v0.get('compaction', 'on (default)')}\n")

    bad = 0
    for n in names:
        cfg = cfgs[n]
        ds = diff(v0, cfg) if n != "V0" else []
        print(f"=== {n}")
        for d in ds:
            print("   ", d)
        if not ds:
            print("    (identical to V0)")
        # A Magic Context variant without built-in compaction off is the mistake this check exists for.
        plugins = cfg.get("plugin", [])
        comp = cfg.get("compaction", {})
        if any("magic-context" in p for p in plugins) and (comp.get("auto") is not False or comp.get("prune") is not False):
            print(f"    FAIL {n}: loads Magic Context but compaction is {comp or 'on (default)'}; the plugin needs it off")
            bad += 1
        # Plugins must be pinned: an unpinned spec would install whatever is newest at run time.
        for p in plugins:
            if not (p.startswith("./") or "@" in p):
                print(f"    FAIL {n}: plugin {p!r} is not pinned")
                bad += 1
        # Every {env:X} the config references must be a key run_trial.sh passes to the container.
        raw = json.dumps(cfg)
        used = sorted(alias for env, alias in KEY_ENV.items() if "{env:%s}" % env in raw)
        unknown = set(re.findall(r"\{env:([A-Z0-9_]+)\}", raw)) - set(KEY_ENV)
        if unknown:
            print(f"    FAIL {n}: references env(s) run_trial.sh does not pass: {sorted(unknown)}")
            bad += 1
        print(f"    keys: {used or ['none']}")

    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
