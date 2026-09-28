# Batch 8: mini v3, loop breaker (28 Sept 2026)

The npm package's one-file bundle at v3, run with `--no-sandbox` inside the same trial container
as the Python versions. Same tasks, model and settings as batches 5–7 (T1, T2, T6 × 3,
`vllm-qwen3.8-nothink`). v3 adds a workspace-fingerprint loop breaker (a nudge at 8 idle tool
calls after the first file change, a firmer one at 16), a requirement-checklist prompt, and
retries that survive a ~3-minute gateway outage. Per-run data: `batch-8.json`.

| Run | Result | Hidden | Min | Calls | Tokens in / out | Peak prompt | Nudges |
|---|---|---|---|---|---|---|---|
| mini3-t1-1 | PASS | 4/4 | 11.5 | 46 | 756,088 / 7,278 | 25.4k | 2 |
| mini3-t1-2 | PASS | 4/4 | 15.8 | 67 | 1,289,606 / 10,474 | 30.6k | 3 |
| mini3-t1-3 | PASS | 4/4 | 5.1 | 25 | 328,675 / 4,242 | 20.4k | 0 |
| mini3-t2-1 | PASS | 8/8 | 8.6 | 18 | 284,688 / 5,830 | 26.1k | 0 |
| mini3-t2-2 | **FAIL** | 6/8 | 7.8 | 16 | 223,310 / 5,309 | 25.7k | 0 |
| mini3-t2-3 | PASS | 8/8 | 9.2 | 17 | 272,183 / 6,205 | 26.8k | 0 |
| mini3-t6-1 | PASS | 5/5 | 2.5 | 16 | 113,660 / 2,505 | 8.1k | 0 |
| mini3-t6-2 | PASS | 5/5 | 1.6 | 16 | 123,459 / 1,936 | 7.3k | 0 |
| mini3-t6-3 | PASS | 5/5 | 1.7 | 5 | 27,441 / 1,010 | 7.3k | 0 |

No T6 trap followed; no API errors; no vLLM restart; no retries fired.

**The one failure (t2-2) is a one-word bug, not a loop regression.** The collector merge loop
iterated `("enrollments", "completions", "refunds")` and did `row.get(column)`, but the CSV column
(and the metric) is `refunds_eur` — so `course_refunds_eur` was always emitted as `failed(...)`
and two hidden tests missed. The other two T2 runs used `refunds_eur` correctly and passed, as did
every T2 run in batches 6 and 7. The loop breaker is unrelated to the mistake.

## v3 vs the earlier versions

| | v1 (batch 5) | v2 (batch 6) | TypeScript 0.2.x (batch 7) | **v3 (batch 8)** |
|---|---|---|---|---|
| Passed | 9/9 | 9/9 | 9/9 | **8/9** |
| Median time | 6.5 min | 9.5 min | 8.4 min | **7.8 min** |
| Median calls | 23 | 20 | 22 | **17** |
| Median tokens in | 273k | 272k | 309k | **272k** |
| Total time | 60 min | 76 min | 73 min | **64 min** |
| Total calls | 222 | 222 | 275 | **226** |
| Total tokens in | 2.53M | 3.80M | 3.96M | **3.42M** |
| Peak prompt | – | 41.7k | 29.4k | 30.6k |

| Task (sum of 3) | v1 | v2 | TypeScript 0.2.x | v3 |
|---|---|---|---|---|
| T1 | 21 min / 96 / 1.34M | 27 min / 90 / 1.54M | 36 min / 152 / 2.44M | 32 min / 138 / 2.37M |
| T2 | 27 min / 71 / 0.91M | 36 min / 92 / 2.01M | 32 min / 77 / 1.27M | 26 min / 51 / 0.78M |
| T6 | 11 min / 55 / 0.28M | 14 min / 40 / 0.26M | 5 min / 46 / 0.25M | 6 min / 37 / 0.26M |

**Reading:** the loop breaker works. Against the same TypeScript bundle at 0.2.x (batch 7), v3
cuts total calls 18% (275 → 226), total tokens in 14% (3.96M → 3.42M), and T2's tokens by 39%
(1.27M → 0.78M). T1's self-check loop is the target and it shrank: two of three runs still nudged,
but the expensive first run fell from 67 calls to 46, and no run hit the 60-step limit (batch 7's
t1-1 did). The single failure is the `refunds` key slip above, not the loop. With 9 runs the
difference is consistent in direction but not yet statistically strong; the cheaper per-task
totals (especially T2) are the clearest signal.

Raw per-run figures: `batch-8.json`. Method: [[Test Method]]. Tasks: [[Tasks]].
