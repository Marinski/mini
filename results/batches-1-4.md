# Batches 1–4: the retry/backoff task (26–27 Sept 2026)

One task for all four batches: retry with backoff in a data-pipeline repo, 14 hidden tests
(see `trial/tasks/README.md`). Models: `vllm-qwen3.8` (Qwen 3.8, thinking **on**) and
`vllm-qwen3.8-nothink` (thinking **off**), plus Gemma in batch 2. Runs stop at 45 minutes.
Calls = model requests, Tools = tool calls, tokens from the gateway's spend logs.

## Batch 1: Qwen, thinking on, agents on the host

| Run | Result | Hidden | Min | Calls | Tools | Tokens in / out |
|---|---|---|---|---|---|---|
| opencode-1 | PASS | 14/14 | 33.5 | 17 | 20 | 519k / 21k |
| opencode-2 | PASS | 14/14 | 20.3 | 11 | 15 | 217k / 11k |
| pibox-1 | PASS | 14/14 | 26.3 | 15 | 18 | 276k / 17k |
| pibox-2 | PASS | 14/14 | 21.4 | 13 | 14 | 192k / 13k |
| Claude Agent SDK-1 | TIMEOUT | 1/14 | 45 | 8 | – | 153k / 1.6k (13 API errors) |
| Claude Agent SDK-2 | TIMEOUT | 9/14 | 45 | 14 | – | 259k / 13k (10 API errors) |

## Batch 2: Qwen (thinking on) vs Gemma

| Run | Result | Hidden | Min | Calls | Tools | Tokens in / out |
|---|---|---|---|---|---|---|
| opencode-qwen-1 | PASS | 14/14 | 45.0 | 17 | 25 | 558k / 27k |
| opencode-qwen-2 | PASS | 14/14 | 25.3 | 13 | 14 | 331k / 15k |
| pibox-qwen-1 | PASS | 14/14 | 30.4 | 16 | 20 | 277k / 19k |
| pibox-qwen-2 | PASS | 14/14 | 22.8 | 10 | 11 | 165k / 14k |
| SDK-qwen-1 | TIMEOUT | 0/14 | 45 | 7 | 11 | 114k / 3.4k (3 API errors) |
| SDK-qwen-2 | PASS | 14/14 | 45 | 8 | 10 | 138k / 3.1k (4 API errors) |
| opencode-gemma-1 | FAIL | 0/14 | 0.1 | 4 | 3 | 56k / 56 |
| pibox-gemma-1 | FAIL | 1/14 | 15.7 | 6 | 5 | 42k / 18k |
| SDK-gemma-1 | FAIL (broke old tests) | 14/14 | 21.2 | 52 | 51 | 1.97M / 38k |

## Batch 3: Qwen thinking off vs on (after a gateway routing fix)

"Native" = the Claude Agent SDK talking to vLLM's own Anthropic-style endpoint, thinking on.

| Run | Result | Hidden | Min | Calls | Tools | Tokens in / out |
|---|---|---|---|---|---|---|
| opencode, off | PASS | 14/14 | 6.8 | 13 | 17 | 196k / 3.6k |
| pibox, off | PASS | 14/14 | 8.7 | 11 | 13 | 123k / 5.0k |
| pibox, on | PASS | 14/14 | 24.4 | 12 | 15 | 210k / 15k |
| SDK, off-1 | PASS | 14/14 | 12.3 | 35 | 36 | 778k / 7.0k |
| SDK, off-2 | PASS | 14/14 | 15.1 | 37 | 38 | 943k / 9.1k |
| SDK, native-1 | PASS | 14/14 | 41.5 | 16 | 20 | 482k / 23k |
| SDK, native-2 | PASS | 14/14 | 61.8 | 18 | 22 | 717k / 34k |

## Batch 4: new harnesses, thinking off, each run in its own container

| Run | Result | Hidden | Min | Calls | Tools | Tokens in / out |
|---|---|---|---|---|---|---|
| Copilot CLI-1 | PASS | 14/14 | 5.9 | 10 | 11 | 169k / 3.5k |
| Copilot CLI-2 | PASS | 14/14 | 9.5 | 21 | 28 | 412k / 5.8k |
| opencode-1 | PASS | 14/14 | 14.9 | 33 | 33 | 709k / 9.0k |
| opencode-2 | PASS | 14/14 | 8.5 | 20 | 21 | 340k / 5.2k |
| Qwen Code-1 | PASS | 14/14 | 19.1 | 36 | 41 | 1.31M / 11k |
| Qwen Code-2 | PASS | 14/14 | 16.8 | 26 | 28 | 783k / 10k |
| mini v1-1 | PASS | 14/14 | 7.0 | 24 | 15 | 171k / 5.0k |
| mini v1-2 | FAIL | 12/14 | 7.4 | 16 | 15 | 120k / 4.4k |

## Takeaways

- Thinking off was 3–4× faster than thinking on for the same pass rate, so every later batch
  runs with thinking off.
- Gemma went 0 for 3; later batches are Qwen only.
- Runs discarded and not counted: three spoiled by gateway restarts, five from a first batch 3
  attempt, two invalid Agent SDK runs (one escaped its sandbox and edited the real repo, which is
  why every later run is in a container mounting only its own repo copy).
