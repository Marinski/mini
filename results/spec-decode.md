# Speculative-decoding experiments — Qwen3.8-27B on the GX10 head

Goal: raise decode throughput above the ~10.9 tok/s baseline without the MTP
corruption bug (#53912, #47194) that forced MTP off on 25 Sept.

Environment: vLLM v0.30.0 (pinned digest), Qwen3.8-27B NVFP4, `--max-model-len
262144`, `--gpu-memory-utilization 0.40`, `--no-async-scheduling`,
`--enable-prefix-caching`, FLASHINFER attention. Harness bench:
`~/repos/mini/trial` (mini / opencode / pibox on tasks t1 t2 t6).

Measurement note: under spec decode `vllm:inter_token_latency_seconds` no longer
maps 1:1 to output tokens (a 320-token reply logged ~394 "iters"), so the
primary metric is **wall-clock completion_tokens / seconds** from
`~/agent-trials/probe_spec.py` (one 320-token code-echo prompt + one prose
prompt, 3 reps each, after a warm-up request).

## Iteration 0 — baseline (no speculative decoding)

| prompt | tok/s (3 reps) |
|---|---|
| code-echo | 10.90, 10.89, 10.89 |
| prose | 10.90, 10.89, 10.90 |

Steady **10.89–10.90 tok/s**, independent of prompt type and output length.
Cumulative container average at the time: 112.0 ms/token.

## Iteration 1 — n-gram speculative decoding

Flag:
```
--speculative-config={"method":"ngram","num_speculative_tokens":5,"prompt_lookup_max":4,"prompt_lookup_min":2}
```

Acceptance (warm-up + probe): 92 accepted / 254 drafted = **36.2%**;
1.80 accepted tokens per 5-token draft step.

| prompt | tok/s (3 reps) | vs baseline |
|---|---|---|
| code-echo | 14.33, 14.88, 17.30 (mean 15.50) | **+42%** |
| prose | 12.50, 12.65, 12.28 (mean 12.48) | **+15%** |

Config-side notes / costs:
- Forced to the **V1 model runner**: "Model Runner V2 does not yet support
  speculative method 'ngram'". Still a net gain.
- `min_p` and `logit_bias` are disabled under speculative decoding.
- KV cache shrinks 652,346 -> 529,986 tokens (2.49x -> 2.02x concurrency at
  262k context) because the runner reserves memory for the extra tokens.
- n-gram verification is exact (the model checks the draft), so it is
  distribution-preserving: no quality risk expected. Harness pass rates
  (`~/agent-trials/spec-ngram/REPORT.md`) confirm.

## Iteration 2 — re-enable async scheduling with n-gram (4 Oct 2026)

Goal: the 26 Sept freeze suspect, `--async-scheduling`, tested beside n-gram.
Run on the head from the backtester over the worker; probe `~/agent-trials/probe_spec.py`
(one 320-token code-echo + one prose prompt, 3 reps, warm-up first). The engine was
idle (agentpipe run9243 finished) before each run; each run recreated one container.

### 2a — as specified (CPU n-gram + `--async-scheduling`) — **rejected by vLLM 0.30.0**

The container would not start:

```
Value error, Currently, async scheduling is only supported with EAGLE/MTP/Draft
Model/NGram GPU/DSpark kind of speculative decoding
```

Async scheduling is incompatible with the **CPU** n-gram method on hybrid
Mamba/GDN. Startup crash-looped; rolled back to Iter-1 within the minute.

### 2b — corrected to GPU n-gram (`ngram_gpu` + `--async-scheduling`)

`ngram_gpu` takes the same params and *is* on the allowed list, so it came up
(health 200 after 430 s). 2c is the control that isolates async: same `ngram_gpu`,
async off. Iter-1 was re-measured for a same-day baseline.

| config | code-echo tok/s | prose tok/s | accepted tokens / draft step |
|---|---|---|---|
| Iter-1, CPU n-gram, async off (re-measured) | 18.40 | 12.24 | 494 / 287 = 1.72 |
| Iter-2c, `ngram_gpu`, async **off** (control) | 18.85 | 11.96 | 509 / 1413 = 0.36 |
| Iter-2b, `ngram_gpu`, async **on** | 19.96 | 12.14 | 563 / 1360 = 0.41 |

- **Isolated effect of async** (2b vs 2c): code-echo **+5.9%**, prose **+1.5%** —
  real but small.
- **`ngram_gpu` vs CPU n-gram** (2c vs Iter-1, both async off): code +2.4%,
  prose −2.3% — a wash.
- **Vs the 10.89 tok/s baseline**, Iter-2b is code **+83%**, prose **+11%**. The
  win is still n-gram itself, not async.
- Caveat: the accepted/draft-step ratio collapses from 1.72 (CPU n-gram) to ~0.4
  (`ngram_gpu`) while throughput holds up, so the two methods clearly count drafts
  differently; do not read the raw ratio across methods.
- No freeze during these short runs, but the 26 Sept freeze happened under async
  scheduling. The freeze watchdog (`vllm-freeze-watchdog.timer`) **is installed
  and active on the backtester** (it polls both head models every minute and posts
  to the agentpipe Discord), and Iter-2b was soaked (below). Quality for `ngram_gpu`
  is still unproven (exact verification expected to preserve it, but the harness has
  not run on `ngram_gpu`).

Decision: **left the head on Iter-1** (CPU n-gram, async off) pending review; the
`ngram_gpu`/async configs were rolled back after measurement. The prepared change
and all raw JSON live in `~/agent-trials/spec-async/`.

## Iteration 2 — soak of `ngram_gpu` + async (5 Oct 2026)

Iter-2b was switched in on the head and soaked for 30 min with a synthetic
concurrency-6 load (`~/agent-trials/spec-async/soak.py`: 50k-token prefill,
echo-decode and chat shapes), watchdog armed throughout:

| metric | value |
|---|---|
| requests | 252 (84 each of long / echo / chat) |
| errors | 0 |
| generated / prompt tokens | 65,891 / 10,158,456 |
| mean latency — long / echo / chat | 16.6 s / 25.2 s / 43.4 s |
| freezes | **none** — container never restarted, watchdog never fired |

Caveats: this is not the 26 Sept shape — prompts were ≤50k tokens at concurrency 6,
whereas the hang came from ~240k-token agent prefixes. The engine logs
`Model Runner V2 does not yet support 'ngram_gpu'; using the V1 model runner instead`.

### Real-traffic soak (5 Oct, ~1h54m)

Iter-2b was then driven with the actual agent harnesses through the gateway
(`~/agent-trials/spec-ngram-soak`, mini/opencode/pibox × t1/t2) — real long-prefix
agent loops, i.e. the 26 Sept shape — watchdog armed throughout.

**Stability: clean.** 13:23→15:17, 6 runs, ~2h wall: no freeze, `vllm-qwen3.8`
never restarted, watchdog never fired. Async scheduling did not reproduce the hang
under ~2h of real traffic.

**Quality: mixed (single rep each, so likely agent-loop variance):**

| harness | Iter-1 (CPU n-gram) | Iter-2b (`ngram_gpu` + async) |
|---|---|---|
| mini | t1 PASS 4/4 · 16.7m · t2 PASS 8/8 · 6.8m | t1 PASS 4/4 · 2.8m · t2 **FAIL 0/8** · 6.6m |
| opencode | t1 PASS 4/4 · 7.0m · t2 TIMEOUT 0/8 · 21.1m | t1 PASS 4/4 · 7.1m · t2 FAIL 0/8 · 5.3m |
| pibox | t1 FAIL 1/4 · 32.4m · t2 FAIL 8/8 · 44.9m | t1 **PASS 4/4** · 45.3m · t2 FAIL 0/8 · 44.9m |

t2 is flaky under both configs (opencode and pibox fail it either way); mini t2
swung PASS→FAIL and pibox t1 FAIL→PASS, so no consistent direction. n-gram
verification is exact, so the swing is more likely agent-loop variance than the
spec method — but one rep cannot settle it.

Decision after both soaks: **rolled back to Iter-1**. Stability held, but async's
isolated gain is only ≤6% and the quality signal is inconclusive; the prepared change
stays in `~/agent-trials/spec-async/`.

## Next

- Iteration 2 proper is spent: async only exists with a GPU/draft spec method, its
  isolated gain is ≤6%, and ~2h of real traffic showed no stability win to chase.
  Revisit only with multi-rep quality runs on `ngram_gpu` if the +6% matters.
- Iter-1 quality rows are complete (all 9 in `~/agent-trials/spec-ngram`): mini 3/3,
  opencode 2/3, pibox 1/3 across t1/t2/t6.
- Iteration 3: DFlash2 (`z-lab/Qwen3.8-27B-DFlash2`) — house recipe, but needs
  `--load-format instanttensor`, ~0.7 gpu-mem, and a quality check because
  DFlash + prefix caching caused accuracy issues on the sibling Qwen3.6-fp8.
