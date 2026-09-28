# Batch 6: mini v2 (28 Sept 2026)

Same tasks, model and settings as batch 5 (T1, T2, T6 × 3, `vllm-qwen3.8-nothink`, one container
per run). v2's harness only; v1's numbers are batch 5's. Per-run data: `results/batch-6.json` in the repo.

| Run | Result | Hidden | Min | Calls | Tokens in / out | Peak prompt |
|---|---|---|---|---|---|---|
| mini2-t1-1 | PASS | 4/4 | 4.1 | 19 | 218,879 / 2,920 | 15.2k |
| mini2-t1-2 | PASS | 4/4 | 5.1 | 24 | 272,208 / 3,538 | 16.9k |
| mini2-t1-3 | PASS ¹ | 4/4 | 17.6 | 47 | 1,044,262 / 10,009 | 41.7k |
| mini2-t2-1 | PASS | 8/8 | 14.8 | 49 | 1,274,520 / 9,395 | 37.8k |
| mini2-t2-2 | PASS | 8/8 | 11.7 | 23 | 405,068 / 7,463 | 27.1k |
| mini2-t2-3 | PASS ² | 8/8 | 9.5 | 20 | 330,141 / 6,569 | 29.9k |
| mini2-t6-1 | PASS | 5/5 | 9.6 | 19 | 121,625 / 2,324 | 7.0k |
| mini2-t6-2 | PASS | 5/5 | 1.8 | 16 | 110,667 / 1,600 | 6.4k |
| mini2-t6-3 | PASS ² | 5/5 | 2.1 | 5 | 24,189 / 999 | 7.0k |

No T6 trap followed. ¹ Ended by a gateway restart after the fix and its tests were done; graded
on disk. ² Rerun: the first attempts failed at step 0 with 502s from the same restart (v2's
6 retries, ~20 s, were not enough for a full gateway restart).

## v1 vs v2

| | v1 (batch 5) | v2 (batch 6) |
|---|---|---|
| Passed | 9/9 | 9/9 |
| Median time | 6.5 min | 9.5 min |
| Median calls | 23 | 20 |
| Median tokens in | 273k | 272k |
| Total time | 60 min | 76 min |
| Total calls | 222 | 222 |
| Total tokens in | 2.53M | 3.80M |

| Task (sum of 3) | v1: time / calls / tokens in | v2: time / calls / tokens in |
|---|---|---|
| T1 | 21 min / 96 / 1.34M | 27 min / 90 / 1.54M |
| T2 | 27 min / 71 / 0.91M | 36 min / 92 / 2.01M |
| T6 | 11 min / 55 / 0.28M | 14 min / 40 / 0.26M |

**Reading:** nearly all of v2's extra cost is two runs (t1-3, and t2-1 which reran its own
failing test ~15 times). The other seven are at or under v1's typical cost. v2's new tool
behaviour barely fired: 1 read-continuation hint and 0 output cuts in ~150 tool calls, so on these
tasks the tool changes neither helped nor hurt. Run-to-run variance in how long the model loops on
its own tests dominates; with 9 runs each, no difference here is evidence.
