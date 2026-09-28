# Results

- [[Results Batches 1-4]]: the retry/backoff task; thinking on vs off; Qwen vs Gemma; first mini runs
- [[Results Batch 5]]: six harnesses × three tasks × three runs
- [[Results Batch 6]]: mini v2, and v1 vs v2
- [[Results Batch 7]]: mini in TypeScript, and v1 vs v2 vs TypeScript

## All Qwen runs, by harness

| Harness | Batches | Passed | Notes |
|---|---|---|---|
| mini v1 | 4, 5 | 10/11 | fastest median on batch 5 |
| mini v2 | 6 | 9/9 | |
| mini TypeScript | 7 | 9/9 | the npm package |
| opencode | 1–5 | 16/16 | |
| pibox (pi) | 1–5 | 14/15 | fewest tokens among full harnesses |
| Hermes Agent | 5 | 9/9 | slowest, ~1.7M tokens per run |
| Copilot CLI | 4, 5 | 8/11 | loops until the limit on harder tasks (up to 24M tokens) |
| Aider | 5 | 6/9 | fails when edits span several files |
| Qwen Code | 4 | 2/2 | ~1M tokens per run |
| Claude Agent SDK | 1–3 | 5/8 | all failures before the gateway routing fix |
| Any harness on Gemma | 2 | 0/3 | |
