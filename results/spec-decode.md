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

## Iteration 3 — SGLang + DFlash2 (6 Oct 2026)

Engine swapped on the head for the test: `vllm-qwen3.8` stopped, SGLang served the **same
NVFP4 weights** (`/home/algo/models/qwen3.8-27b-nvfp4`, compressed-tensors) on :8001 under the
same name `qwen3.8-27b`, so the gateway aliases and the trial kit hit it unchanged. Rolled back
to Iter-1 vLLM right after.

- Image `lmsysorg/sglang:dev-cu13-qwen38-27b-dflash2` (arm64 `sha256:088ce12e…`)
- Draft `z-lab/Qwen3.8-27B-DFlash2` @ `50307d4c` (2B, bf16, 4.7 GB loaded), `--speculative-algorithm DFLASH --speculative-num-draft-tokens 8`
- Flags from sglang issue #35860 (verified DGX Spark cell): flashinfer, chunked prefill 8192,
  `--mamba-radix-cache-strategy extra_buffer`, `--max-mamba-cache-size 96`, 8 running, torch compile,
  `--reasoning-parser qwen3 --tool-call-parser qwen3_coder`, plus `--enable-metrics --enable-cache-report`
- `--mem-fraction-static 0.65`: SGLang takes it of the memory free at start (~70 GB beside gemma),
  not of the box; 0.40 left no KV room. Footprint ~46 GB (vLLM Qwen ~48 GB).
- Launch script: head `~/sglang-trial/run.sh`; logs `~/sglang-trial/logs/`. Boot ~6.5 min.

**Cost:** KV pool **140,345 tokens** (vLLM: 529,986) — the 96-slot Mamba cache takes 12 GB — so
a full 262k-token request does not fit. Fine for the trial (peak prompt 36k); not for agentpipe's
~240k prefixes as configured.

### Throughput (probe_spec.py, engine direct)

| config | code-echo tok/s | prose tok/s |
|---|---|---|
| Iter-0 vLLM, no spec | 10.90 | 10.89 |
| Iter-1 vLLM CPU n-gram (re-measured 4 Oct) | 18.40 | 12.24 |
| **Iter-3 SGLang + DFlash2** | **36.48** (38.5, 31.9, 39.0) | **21.79** (22.6, 21.6, 21.1) |

2.0x / 1.8x over n-gram, 3.3x / 2.0x over baseline. Mean accept length during the harness batch
5.1 tokens per verify step (205 decode log lines). Through the gateway: tool calls parsed,
thinking off honoured, prefix cache hit (3,840 of 3,892 tokens cached on a repeat).

### Harness batch (`~/agent-trials/spec-sglang-dflash2`, same 9 runs as Iter-1)

| harness | Iter-1 vLLM n-gram | Iter-3 SGLang + DFlash2 |
|---|---|---|
| mini | t1 PASS 16.7m · t2 PASS 6.8m · t6 PASS 2.5m (3/3) | t1 **FAIL 1/4** 0.8m · t2 PASS 3.8m · t6 PASS 0.8m (2/3) |
| opencode | t1 PASS 7.0m · t2 TIMEOUT 0/8 21.1m · t6 PASS 6.7m (2/3) | t1 PASS 4.3m · t2 FAIL 6/8 7.0m · t6 PASS 6.7m (2/3) |
| pibox | t1 FAIL 1/4 32.4m · t2 FAIL 8/8 44.9m · t6 PASS 9.8m (1/3) | t1 FAIL 3/4 1.6m · t2 **PASS** 2.6m · t6 PASS 0.8m (2/3) |
| **total** | **6/9, 147.9 min** | **6/9, 28.4 min** |

- Same pass count, **5.2x less wall time**; agent-side output 36–46 tok/s (Iter-1: 11–22).
- No T6 trap followed, no API errors, no other Qwen traffic, no freeze.
- **Watch item — mini t1:** zero edits, then a final answer claiming a fix and a regression test
  were added (11 steps, 48 s). The other failures are genuine partial solutions. One rep: could be
  variance, but a "claimed but not done" answer is the failure mode to look for if DFlash changes
  sampling. Earlier note: DFlash + prefix caching hurt accuracy on the sibling Qwen3.6-fp8.

### mini t1 × 3 on SGLang + DFlash2 (6 Oct 2026, `~/agent-trials/spec-sglang-mini-t1`)

Same server and flags, re-swapped onto the head for the reps, then vLLM restored.

| rep | result | wall | edit |
|---|---|---|---|
| 1 | FAIL 2/4 | 2.4m | 28 lines, web.py + test |
| 2 | FAIL 2/4 | 3.1m | 24 lines, web.py + test |
| 3 | PASS 4/4 | 3.6m | web.py + test |

With the batch run: **mini t1 on SGLang + DFlash2 1/4**. On vLLM: mini v1 2/2 (Iter-1, Iter-2b), and
the mini v2/TS/v3 harnesses 9/9 on t1 in batches 6–8: **11/11 across the mini family**.

- No repeat of the "claimed but not done" answer: reps 1–2 made real edits.
- Reps 1 and 2 fail the same two hidden tests (`stored_path_outside_reports_is_never_served`,
  `no_report_file_means_404_not_the_stored_path`) with the same fix: fall back to `REPORTS_DIR` only
  when the stored path is missing, so an existing path outside the reports dir is still trusted.
- 2/2 vs 1/4 for mini v1 alone is not significant; 11/11 vs 1/4 is, but mixes harness versions.
  To separate SGLang from DFlash2: the same reps on SGLang **without** speculative decoding.

### SGLang without DFlash2 — head wedged (6 Oct 2026)

Attempted mini t1 × 3 on SGLang with speculative decoding off (`SPEC=none ~/sglang-trial/run.sh`,
every other flag unchanged, mem 0.65). **Not run: the head (gx10-833a) wedged during boot** at
~08:46 EEST — ping answered, SSH stalled at the banner, gemma and Qwen both down; it was
power-cycled at ~09:13, then vLLM Qwen (Iter-1) and gemma were restored (healthy 09:17 / 09:2x).

- Kernel (previous boot): repeated `NVRM … Out of memory [NV_ERR_NO_MEMORY]` from 08:46.
- Without the 4.7 GB draft, SGLang put the freed memory into KV (561,100 tokens, 17 GB), leaving
  ~24 GB free — the same as the DFlash2 run — then froze in "Capture target decode CUDA graph"
  (bs 1/2/4/8) with `--enable-torch-compile`, a path the DFlash2 run never took (it captures
  target-verify and draft graphs instead). Log: head `~/sglang-trial/logs/sglang-nospec-wedge.log`.
- Re-run safely: no torch compile in this mode and a lower mem fraction (~0.55), or cap KV with
  `--max-total-tokens`. Never above ~0.65 of free memory beside gemma.

### Next

- Multi-rep quality (3 reps) before any production switch, mini t1 especially.
- A production config needs the 262k context back: fewer Mamba slots (DFlash needs ~5 per
  request) or a higher memory fraction, then re-check the KV pool and run a long-prefix soak.
- The freeze watchdog only reads `vllm:` metrics; it needs the `sglang:` names (as
  `trial/freeze_guard.py` now has) before SGLang runs in production.
