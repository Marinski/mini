# mini bench: a local copy of the Protorikis Bench suite

> Spec only. Runs continue on [Protorikis Bench](https://bench.protorikis.com) meanwhile; their
> results are the reference this tool must match.

## Goal

Run the eight [Protorikis Bench](https://bench.protorikis.com) benchmarks ourselves, against any
OpenAI-compatible endpoint, with our own prompts, our own checking and our own results files:
- no free-plan limits (10 runs, 50 jobs, 500 jobs/day, 2,000 prompts/day, a concurrent-job cap);
- no prompts or answers leaving the network;
- results in `results/`, next to the agent-trial batches, in the same per-model tables.

Protorikis stays the reference: each benchmark here is checked against a Protorikis run of the
same model before we trust it (step 9).

## How Protorikis works (what we copy)

Read from its API and from its agent, [`rikis`](https://github.com/protorikis/rikis) (Apache-2.0,
v0.0.4), on 6 Oct 2026:

| Part | Protorikis | mini bench |
|---|---|---|
| Benchmark definitions (prompts, checks, profiles) | on their server; prompt texts are not exposed, only labels | our own, in `bench/suites/` |
| Scheduling | web app; the agent polls `POST /api/jobs/next` | CLI: `bench run <suite> --endpoint … --model …` |
| Inference | `rikis` streams each prompt to `<runtime>/v1/chat/completions` (no API key) | the same, plus an optional API key |
| Timing | TTFT = first content or reasoning chunk; tok/s = chunks ÷ (end − first chunk) | the same, plus server token counts (see "Measurements") |
| Multi-turn | replays the conversation; with `preserve_thinking` the reasoning goes back inside `<think>` | the same |
| Checking | server-side; HumanEval runs in a container | local; HumanEval in a throwaway Docker container with no network |
| Parameters seen | `{"thinking": false, "multi_turn": true, "temperature": 0}` | per suite, the same defaults |

`rikis` never runs generated code. Its token count is the number of streamed chunks, which
over- or under-counts when a server sends several tokens per chunk (MTP, speculative decoding).

## The suite

| id | What it tests | Pass check (Protorikis) | Shape on Protorikis (jobs / prompts / largest prompt) |
|---|---|---|---|
| `hello_world` | Recall from a shared context; pipeline smoke test ("state your model name…", two yes/no questions) | each prompt checked | 1 / 3 / 181 B |
| `multi_turn_1` | Multi-turn works: two numbers given in turns 1–2, recalled and summed in turns 3–4 ("print only the number") | each prompt checked | 1 / 4 / 224 B |
| `multi_turn_2` | KV-cache reuse in a growing conversation: three turns each add 500 lines of code, the fourth adds 1 line and measures how fast the cached context answers | each prompt checked; turn 4 = cache speed | 1 / 4 / 191 KB |
| `preserve_thinking_1` | Reasoning is kept across turns (thinking on, reasoning re-sent) | each prompt checked | 1 / 2 / 227 B |
| `context_caching_1` | KV reuse across 4 context windows of 500 different source lines; each chunk sent cold, then again (`-rep`) | TTFT of every repeat < 5 s | 8 / 16 / 115 KB, up to 64K tokens |
| `memory_recall_1` | Verbatim recall of function bodies after the opening brace; 20-line window plus up to 80 continuation lines; > 100 lines out = fail | first 8 lines exact, no missing or extra lines | profiles `eighths` 8/16/192 KB, `quarters` 4/16/271 KB, `halves` 2/16/383 KB, `full` 1/16/650 KB |
| `human_eval` | 164 Python problems: signature + docstring in, function body out | all asserts pass (run in a container) | 1 / 164 / 1.5 KB |
| `finqa` | 1,147 numerical questions over S&P 500 earnings-report excerpts with a table | final answer = gold value within tolerance (exact for yes/no) | 1 / 1,147 / 9.4 KB |

The code-context benchmarks (`multi_turn_2`, `context_caching_1`, probably `memory_recall_1`) use
[three.js](https://github.com/mrdoob/three.js) source (MIT), which Protorikis credits.

## Design

### Layout

```
bench/
  bench.py            CLI: run, list, report, compare
  client.py           streaming OpenAI client + timing
  suites/             one module per benchmark: build_prompts(profile, ctx) -> jobs; check(job, results)
  data/               pinned inputs: three.js at a fixed tag, HumanEval, FinQA (fetched by setup)
  sandbox/            Dockerfile for the HumanEval runner (python:3.12-slim, no network)
  report.py           results JSON -> Markdown tables (per model × benchmark)
test/bench/           unit tests for checks and the client (no model calls)
```

Python, like the trial kit (`trial/*.py`), standard library plus `httpx` (see Question 1).

### Model of a run

- **Run** = one benchmark × profile × endpoint × model, with its parameters (`thinking`,
  `temperature`, `multi_turn`, `preserve_thinking`, `max_tokens`).
- **Job** = one conversation (one prompt, or the turns of a multi-turn job).
- **Sub-job** = one request: label, prompt bytes and tokens, TTFT, generation time, output tokens,
  server-reported prompt and cached tokens, response text, reasoning text, check result
  (`pass`, `fail`, `error` with reason, or `skipped: exceeds context`).
- Output: `results/bench/<run-id>.json` (every sub-job), plus one line per run in
  `results/bench/index.jsonl`.

### Measurements

Per sub-job, all from the streamed response:
- **TTFT**: request sent → first chunk with content or reasoning (as Protorikis).
- **Generation tok/s**: output tokens ÷ (last chunk − first chunk). Output tokens come from
  `usage.completion_tokens` (requested with `stream_options: {"include_usage": true}`); the
  streamed chunk count is recorded too, so our numbers can be compared with Protorikis's.
- **Prefill tok/s**: prompt tokens not served from cache ÷ TTFT, when the server reports
  `prompt_tokens_details.cached_tokens` (vLLM, SGLang, llama.cpp).

### Rules learned on 6 Oct 2026

- **One stream per endpoint.** A lock file per endpoint URL; a second run on the same endpoint
  waits. On 6 Oct two `rikis` agents ran Multi-Turn #1 and #2 at once on a single-slot
  llama-server, and TTFTs of 45–62 s on 24-byte prompts were the result.
- **Know the context window before sending.** Read it from the server (`/v1/models` metadata,
  llama.cpp `/props`, vLLM `max_model_len`) or `--ctx`. A prompt plus history plus `max_tokens`
  that does not fit is recorded as `skipped: exceeds context`, not as a model failure. On 6 Oct,
  Multi-Turn #2's fourth turn and llama-benchy's 64K depth both hit a 65,536-token window as HTTP 400.
- **Temperature 0 is the Protorikis default**, kept for comparability; Qwen 3.8 is known to loop at
  temperature 0 with thinking on, so a looping answer is cut at `max_tokens` and marked as such.

## Steps

Each step lands with its tests, and says how we know it works.

1. **Client and timing.** `client.py` streams one chat completion and returns the sub-job record.
   *Works when:* against the head's Qwen (vLLM) and the Windows llama-server, TTFT and tok/s for
   a 128-token answer are within 10% of llama-benchy's `tg128` at depth 0, and output tokens equal
   `usage.completion_tokens`.
2. **Run model, results file, lock.** `bench run hello_world` writes `results/bench/<id>.json`;
   a second `bench run` on the same endpoint waits for the first.
   *Works when:* two runs started together finish one after the other, and the JSON validates
   against a schema in `test/bench/`.
3. **`hello_world`, `multi_turn_1`, `preserve_thinking_1`.** Our prompts, same shapes; checks are
   exact-match after trimming (numbers, yes/no) and, for `preserve_thinking_1`, that turn 2 can
   only be answered from turn 1's reasoning.
   *Works when:* unit tests pass on recorded good and bad answers, and the head's Qwen passes all
   three, as it does on Protorikis.
4. **Context window detection and `skipped`.** Applied to every suite from here on.
   *Works when:* `multi_turn_2` on a 65,536-token server records turn 4 as `skipped: exceeds
   context` instead of an error.
5. **Code-context data and `multi_turn_2`, `context_caching_1`.** Pinned three.js source cut into
   500-line chunks; cold then repeated requests; the cache-speed check (TTFT < 5 s on repeats).
   *Works when:* on vLLM with prefix caching, repeats have `cached_tokens` > 0 and TTFT < 5 s; with
   `--no-cache` (a unique prefix per request) the same check fails. That proves the check measures
   caching.
6. **`memory_recall_1` with its four profiles.** Pick functions, cut after the opening brace, check
   the first 8 lines exactly and count missing or extra lines within a 100-line limit.
   *Works when:* the checker passes the true function body and fails each of: one changed line in
   the first 8, one missing line, 101 output lines. Profiles that exceed the window are skipped.
7. **`human_eval`.** Dataset from [openai/human-eval](https://github.com/openai/human-eval) (MIT);
   the completion plus the tests run in the `bench/sandbox` container (`--network none`, CPU and
   memory caps, 10 s per problem).
   *Works when:* the 164 canonical solutions pass 164/164 and an empty body fails 164/164.
8. **`finqa`.** Dataset from [czyssrs/FinQA](https://github.com/czyssrs/FinQA); answer extraction
   (last number in the answer, percent and units normalised) and the tolerance check.
   *Works when:* the gold answers pass 1,147/1,147 through the extractor, and the tolerance is the
   one Protorikis uses (Question 5).
9. **Parity with Protorikis.** Run the same model on both for every benchmark Protorikis has
   results for.
   *Works when:* pass/fail per prompt agrees on the deterministic suites (`hello_world`,
   `multi_turn_1`, `human_eval`), pass rates are within the noise on the rest, and TTFT and tok/s
   agree within 10% after accounting for the chunk-vs-token difference.
10. **Report and wiki.** `bench report` renders the per-model tables used on the wiki Results page
    (pass rate, median TTFT, tok/s per benchmark), alongside the agent-trial results.
    *Works when:* the tables for the 6 Oct models match the per-run JSON by hand on two benchmarks.

## Out of scope

- A web UI and job scheduling across machines (the CLI runs one endpoint from one host).
- Uploading to Protorikis.
- New benchmarks beyond the eight; the agent-trial tasks (`trial/`) stay the coding-agent test.

## Questions

1. Python (like the trial kit, and HumanEval needs Python anyway) or TypeScript (like the mini
   package)? The spec assumes Python.
2. Should the prompts imitate Protorikis's closely (same labels, same three.js chunks if we can
   identify the file and version), or is "same shape, our own text" enough? Closer means better
   parity in step 9.
3. Which three.js tag? Protorikis does not say; the largest prompts (115 KB per 500 lines) suggest
   the bundled `three.module.js`.
4. Memory Recall's source: three.js functions too, or another codebase (our own private repos
   would avoid the model having memorised the text)?
5. FinQA's tolerance: Protorikis says "within tolerance" without a number. Use FinQA's own
   evaluation script (rounding to the gold's precision), or a fixed relative tolerance such as 1%?
6. Defaults for `max_tokens` per benchmark? Protorikis does not show them; thinking-on runs need
   far more than thinking-off.
7. Should the runner also go through the aigate gateway (with a key), so spend logs record bench
   traffic like the trials, or always hit the engine directly as Protorikis does?
8. Where should results live: `results/bench/` in this public repo (the prompts and answers would
   be public), or under `$TRIAL_DATA` with only summaries committed?

---

## Answers (recorded 7 Oct 2026)

1. **Python**, standard library plus `httpx` (tests also need `pytest`). Matches the trial kit and HumanEval.
2. **Recovered, then improved.** Protorikis's exact prompt texts *are* recoverable: `rikis` prints each
   label verbatim, so `hello_world`, `multi_turn_1` and `preserve_thinking_1` use the exact strings from
   `~/agent-trials/llama-benchy/rikis-agent.log`. The code-context and QA prompts are ours (Protorikis
   never exposes them); they keep the same shape and the recovered labels (`human_eval` function names,
   `finqa` questions).
3. **three.js r150, `build/three.module.js`, size-matched chunks.** r150's 500 lines are only ~13.6 KB,
   not the spec's 115 KB, so a chunk is sized in bytes (64 KiB ≈ 2,900 lines) to reproduce the 115/191 KB
   prompts and the 65,536-token skip. See `bench/code_context.py`.
4. **three.js** for `memory_recall_1` too — one pinned dataset, credited once. (Our own repos would avoid
   memorisation; kept as a future profile.)
5. **FinQA's own shape.** The last number is extracted (percent/units normalised); the gold is the
   `answer` string when purely numeric (or `yes`/`no`), otherwise `exe_ans`; comparison rounds to the gold
   answer's precision, exact for yes/no. All 1,147 gold answers pass the extractor.
6. **Per-mode defaults with override.** `max_tokens` is 1024 thinking-off, 8192 thinking-on, overridable
   with `--max-tokens`. Protorikis sends no `max_tokens`; ours is a documented deviation.
7. **Direct by default**, gateway optional: pass aigate's URL as `--endpoint` and a key as `--api-key`
   (or `$BENCH_API_KEY`) so spend logs can record bench traffic when wanted.
8. **`results/bench/` in the repo** (public): `<run-id>.json` per run plus `index.jsonl`, beside the
   agent-trial batches.

### Deviations from the table

- `memory_recall_1` grouping is ours: 16 recalls per profile, shown the source up to the opening brace
  preceded by 1/8, 1/4, 1/2 or the whole file (jobs 8/4/2/1). Protorikis's grouping is not exposed.
- `multi_turn_2`/`context_caching_1` prompt wording is ours; the three.js chunks match in size, not in
  bytes (see answer 3).

### Running it

```bash
python bench/data/setup.py                 # fetch three.js, HumanEval, FinQA
python bench/bench.py list
python bench/bench.py run hello_world --endpoint http://host:8001/v1 --model qwen3.8-27b
python bench/bench.py run memory_recall_1 --profile full --endpoint ... --model ...
python bench/bench.py report --out results/bench/REPORT.md
python bench/bench.py compare <run-a> <run-b>
```

Tests (no model calls): `python -m pytest test/bench`.
