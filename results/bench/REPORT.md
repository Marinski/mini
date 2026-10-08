# mini bench results

### qwen3.8-flash-next-iq3_s

| Benchmark | Pass rate | Passed | Median TTFT (s) | Tokens/s | Context |
|---|---|---|---|---|---|
| context_caching_1 | 100% | 16/16 | 3.95 | — | 65536 |
| finqa | 81% | 927/1147 | 1.05 | 93.97 | 65536 |
| hello_world | 100% | 3/3 | 0.66 | 74.28 | 65536 |
| human_eval | 96% | 157/164 | 1.16 | 97.91 | 65536 |
| memory_recall_1 | 100% | 16/16 | 10.63 | 97.58 | 65536 |
| multi_turn_1 | 100% | 4/4 | 0.37 | 77.39 | 65536 |
| multi_turn_2 | 100% | 2/2 | 10.51 | — | 65536 |
| preserve_thinking_1 | 100% | 2/2 | 1.15 | 73.25 | 65536 |

### qwen3.8-flash-next-q2_0

| Benchmark | Pass rate | Passed | Median TTFT (s) | Tokens/s | Context |
|---|---|---|---|---|---|
| context_caching_1 | 100% | 16/16 | 3.58 | — | 65536 |
| finqa | 80% | 913/1147 | 0.86 | 117.13 | 65536 |
| hello_world | 100% | 3/3 | 0.30 | 121.44 | 65536 |
| human_eval | 90% | 148/164 | 0.76 | 135.01 | 65536 |
| memory_recall_1 | 100% | 16/16 | 10.11 | 136.71 | 65536 |
| multi_turn_1 | 100% | 4/4 | 0.27 | 98.78 | 65536 |
| multi_turn_2 | 100% | 2/2 | 9.80 | — | 65536 |
| preserve_thinking_1 | 100% | 2/2 | 0.75 | 115.90 | 65536 |

### qwen38-27b

| Benchmark | Pass rate | Passed | Median TTFT (s) | Tokens/s | Context |
|---|---|---|---|---|---|
| context_caching_1 | 100% | 16/16 | 7.12 | — | 65536 |
| finqa | 80% | 922/1147 | 1.31 | 71.66 | 65536 |
| hello_world | 100% | 3/3 | 0.40 | 60.80 | 262144 |
| human_eval | 90% | 147/164 | 0.51 | 81.05 | 65536 |
| memory_recall_1 | 100% | 16/16 | 37.04 | 60.08 | 65536 |
| multi_turn_1 | 100% | 4/4 | 0.39 | 77.69 | 262144 |
| multi_turn_2 | 100% | 2/2 | 23.06 | — | 65536 |
| preserve_thinking_1 | 100% | 2/2 | 1.38 | 71.63 | 262144 |

Pass rate counts checked prompts only (errors and context skips are excluded). Median TTFT and tok/s are per prompt across the run.
