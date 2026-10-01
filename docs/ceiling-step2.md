# Compaction calibration (step 2)

Where OpenCode actually compacts, measured instead of assumed. The trial's `limit.context` of
45056 with `limit.output` 16384 assumes OpenCode compacts when the prompt reaches
`context - output = 28672`. This records what the probes showed on 1 Oct 2026.

Method: run V0 on t9 (the longest task) at two low limits whose output/context ratio is the
trial's own 4/11, so the *fraction* transfers to 45056. The full prompt of an agent step is
`input + cache.read` from OpenCode's `step_finish` events (the tool-calling call carries the whole
context; a second, smaller per-step call is ignored). Compaction is a >30% drop between consecutive
tool-calling steps.

| Probe | context | output | `context - output` | observed peaks (full prompt) | compaction |
|---|---|---|---|---|---|
| `V0-ctx11k` | 11264 | 4096 | 7168 | ~8232–8750 | constant: the fixed system+tools prefix (~7840 tokens) already exceeds 7168, so it compacts every step — **saturated, not informative** |
| `V0-ctx22k` | 22528 | 8192 | 14336 | 14681, 14396, 15570, 15132 (then drops to 9649, 9063, 12667, 11765) | yes: peaks track `context - output`, not `context` |

`V0-ctx22k` full-prompt series (tool-calling steps):

```
8232, 11536, 14681, 9649, 14254, 14396, 9063, 9166, 9333, 9942, 10633, 10750,
10904, 11077, 11727, 12303, 13817, 14234, 15570, 12667, 13052, 13845, 15132, 11765
```

The peaks (~14.4k–15.6k) sit at `context - output` (14336), not at `context` (22528): the resets
(14681→9649, 14396→9063, 15570→12667, 15132→11765) only make sense if the trigger is ~14k. The
small overshoot above 14336 is the step that grows the prompt past the trigger before the next
compaction pass runs.

## Result

OpenCode compacts at about **`context - output`**. At the trial's `context: 45056`,
`output: 16384`, compaction starts at **~28672 tokens** — exactly the value the spec assumed.

Baselines checked on 30 Sept: t8 peaks at 37,679 and t9 at 61,510, so under a 28672 trigger the
baseline compacts about once on t8 and two or more times on t9, as the trial requires. No change to
`limit.context: 45056` is needed.

`V0-ctx11k` is kept as the saturation witness: below `system+tools + output` the limit is
inoperable, which is why the trial's 45056 (well above the ~7840-token fixed prefix) is the
smallest sensible value and the two probes are deliberately 2× and 4× it.
