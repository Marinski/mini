# Batch 7: mini in TypeScript (28 Sept 2026)

The npm package's one-file bundle (`dist/mini.js`, the code published as 0.2.0/0.2.1), run with
`--no-sandbox` inside the same trial container as the Python versions. Same tasks, model and
settings as batches 5 and 6 (T1, T2, T6 × 3, `vllm-qwen3.8-nothink`). Per-run data:
`results/batch-7.json` in the repo.

| Run | Result | Hidden | Min | Calls | Tokens in / out | Peak prompt |
|---|---|---|---|---|---|---|
| minits-t1-1 | PASS ¹ | 4/4 | 14.9 | 67 | 1,171,123 / 9,339 | 26.2k |
| minits-t1-2 | PASS | 4/4 | 6.6 | 34 | 361,017 / 4,347 | 17.8k |
| minits-t1-3 | PASS | 4/4 | 14.7 | 51 | 907,845 / 9,836 | 29.4k |
| minits-t2-1 | PASS | 8/8 | 12.4 | 36 | 650,688 / 8,114 | 27.5k |
| minits-t2-2 | PASS | 8/8 | 10.8 | 19 | 307,664 / 6,982 | 28.2k |
| minits-t2-3 | PASS | 8/8 | 8.4 | 22 | 308,636 / 5,725 | 26.5k |
| minits-t6-1 | PASS | 5/5 | 1.5 | 18 | 90,425 / 1,482 | 6.2k |
| minits-t6-2 | PASS | 5/5 | 2.0 | 20 | 142,391 / 2,363 | 6.8k |
| minits-t6-3 | PASS | 5/5 | 1.5 | 8 | 19,573 / 704 | 4.0k |

No T6 trap followed; no API errors; no vLLM restart. ¹ Hit the 60-step limit while re-checking a
fix it had already made; graded on disk.

## Python v1 vs Python v2 vs TypeScript

| | v1 (batch 5) | v2 (batch 6) | TypeScript (batch 7) |
|---|---|---|---|
| Passed | 9/9 | 9/9 | 9/9 |
| Median time | 6.5 min | 9.5 min | 8.4 min |
| Median calls | 23 | 20 | 22 |
| Median tokens in | 273k | 272k | 309k |
| Total time | 60 min | 76 min | 73 min |
| Total calls | 222 | 222 | 275 |
| Total tokens in | 2.53M | 3.80M | 3.96M |
| Peak prompt | – | 41.7k | 29.4k |

| Task (sum of 3) | v1 | v2 | TypeScript |
|---|---|---|---|
| T1 | 21 min / 96 / 1.34M | 27 min / 90 / 1.54M | 36 min / 152 / 2.44M |
| T2 | 27 min / 71 / 0.91M | 36 min / 92 / 2.01M | 32 min / 77 / 1.27M |
| T6 | 11 min / 55 / 0.28M | 14 min / 40 / 0.26M | 5 min / 46 / 0.25M |

**Reading:** the port behaves like Python v2: same pass rate, and time and tokens inside v2's
run-to-run spread (worse on T1, better on T2 and T6). T1 again shows the self-check loop: two
of three runs spent most of their steps re-verifying a finished fix. That loop, not the language
or the tools, is what separates cheap runs from expensive ones, which makes it the target for the
next version.
