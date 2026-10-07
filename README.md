# mini

A minimal coding agent (bash / read / edit / write in one chat-completions loop) and the test
bench used to compare it with full coding-agent harnesses on a local model: Qwen 3.8 served by
vLLM behind a LiteLLM gateway. The question: *how much harness does a local model need?*

## Install (npm)

```bash
npm i -g @marinski/mini
export MINI_API_KEY=...              # your OpenAI-compatible key
cd your-project && mini --base-url http://localhost:4000/v1 --model your-model "fix the failing test"
```

`mini` runs the agent in a throwaway Docker container that mounts only the current folder (it
refuses `/` and your home folder); `--image` picks the container image, which needs Node plus
whatever your tests need (default `node:24-bookworm`). `mini --help` lists the options.
Transcripts go to `~/.local/state/mini/`. Needs Node 20+ and Docker.

## Releasing

```bash
npm version patch            # or minor / major: bumps package.json, commits, tags vX.Y.Z
git push --follow-tags       # the Publish workflow tests, publishes to npm, creates the GitHub release
```

Add a `## X.Y.Z` section to `CHANGELOG.md` before bumping; it becomes the release notes.

## Files

| File | What |
|---|---|
| `src/`, `test/` | **mini in TypeScript** (the npm package, v3): v2's tools plus a workspace-fingerprint loop breaker, a requirement-checklist prompt and 3-minute retries. `npm test`: 34 tests. `npm run build` bundles it into one file, `dist/mini.js`. |
| `mini_harness.py` | **v1** (Python): 86 lines. |
| `mini_harness_v2.py` | **v2** (Python): v1 plus pi-style tool behaviour (multi-edit with diff, paged reads, line-aware output cuts, retries). `test_mini_v2.py`: 26 tests. |
| `trial/` | The bench: containers, freeze guard, grader, batch queue, report. Task repos are private. |
| `bench/`, `test/bench/` | **mini bench** (Python): our local copy of the eight [Protorikis Bench](https://bench.protorikis.com) benchmarks, run against any OpenAI-compatible endpoint, with our own prompts, checks and results. See [Bench](#bench-the-protorikis-suite-locally). `python -m pytest test/bench`: 88 tests. |
| `results/` | Every batch: per-run pass/fail, time, calls, tokens. Bench runs go in `results/bench/`. |
| `docs/` | v2 spec; `docs/wiki/` mirrors the wiki. |

## Headline (batches 5–8, 3 tasks × 3 runs, Qwen thinking off)

| Harness | Passed | Median time | Median tokens in |
|---|---|---|---|
| **mini v1** | **9/9** | **6.5 min** | 273k |
| mini v2 | 9/9 | 9.5 min | 272k |
| mini, TypeScript (npm 0.2.x) | 9/9 | 8.4 min | 309k |
| mini v3 (npm, loop breaker) | 8/9 | 7.8 min | 272k |
| opencode | 9/9 | 10.8 min | 402k |
| Hermes Agent | 9/9 | 26.2 min | 1.66M |
| pibox (pi) | 8/9 | 6.9 min | 210k |
| Copilot CLI | 6/9 | 12.9 min | 691k |
| Aider | 6/9 | 18.8 min | 50k |

Details, method and next steps: see the wiki (source in `docs/wiki/`).

## Run it

Only in a container that mounts nothing but the work folder; it runs whatever shell commands the
model asks for.

```bash
docker run --rm -i -v "$PWD:/work" -w /work -v /tmp/mini-out:/out \
  -v /path/to/mini_harness_v2.py:/opt/mini.py:ro \
  -e LITELLM_KEY -e BASE_URL=http://host:4000/v1 -e MODEL=your-model \
  some-python-image-with-openai python3 /opt/mini.py "your task"
```

Env: `LITELLM_KEY` (required), `BASE_URL` (default `http://172.17.0.1:4000/v1`), `MODEL`,
`WORK` (default `/work`), `LOG` (default `/out/transcript.jsonl`).

Tests: `python3 -m pytest -q test_mini_v2.py` (needs `openai` and `pytest`; no network).

## Bench (the Protorikis suite, locally)

`bench/` runs the eight [Protorikis Bench](https://bench.protorikis.com) benchmarks ourselves against
any OpenAI-compatible endpoint — no free-plan limits, no prompts leaving the network, results in
`results/bench/` next to the agent-trial batches. Protorikis stays the reference: each benchmark is
checked against a Protorikis run of the same model before we trust it. **This measures models, not
harnesses** — for harnesses (opencode, Copilot CLI, pibox, Aider, Hermes, mini) use `trial/`.

```bash
python bench/data/setup.py        # once: fetch pinned three.js r150, HumanEval, FinQA (gitignored)
python bench/bench.py list        # the eight suites, their profiles and default parameters

# direct, as Protorikis runs it (add --api-key, or point --endpoint at aigate, to log spend):
python bench/bench.py run hello_world --endpoint http://host:8001/v1 --model qwen3.8-27b
python bench/bench.py run finqa       --endpoint http://host:8001/v1 --model qwen3.8-27b

# memory_recall_1 has four profiles (eighths | quarters | halves | full):
python bench/bench.py run memory_recall_1 --profile full --endpoint ... --model ...
```

Suites: `hello_world`, `multi_turn_1`, `multi_turn_2`, `preserve_thinking_1`, `context_caching_1`,
`memory_recall_1`, `human_eval` (runs in a throwaway Docker container, `--network none`), `finqa`.
Flags: `--ctx` (force a context window), `--max-tokens`, `--temperature`, `--thinking/--no-thinking`,
`--preserve-thinking`, `--api-key`/`$BENCH_API_KEY`, `--results DIR`, `--quiet`.

Each run holds a **lock per endpoint URL**, so a second run on the same endpoint waits rather than
sharing the model — run different endpoints in parallel, one model at a time. A request that would
not fit the context window is recorded as `skipped: exceeds context`, not as a model failure.

Results (`results/bench/`, committed; data and locks are gitignored):

- `results/bench/<run-id>.json` — the whole run: every sub-job's prompt bytes, tokens, TTFT,
  tokens/s (and prefill tokens/s when the server reports cached tokens), chunk count, and pass/fail.
  `<run-id>` = `<suite>__<profile>__<model>__<UTC stamp>`.
- `results/bench/index.jsonl` — one summary line per run.
- `python bench/bench.py report --out results/bench/REPORT.md` — per-model tables (pass rate, median
  TTFT, tokens/s), the same columns as the wiki Results page.
- `python bench/bench.py compare <run-a> <run-b>` — pass/fail agreement and TTFT / tokens/s / chunks/s
  ratios with a 10% flag, for step-9 parity against a Protorikis run.

Design and the answers to the open questions: `docs/SPEC-bench.md`. Tests need no model:
`python -m pytest test/bench` (add `BENCH_DOCKER_TESTS=1` to build and exercise the HumanEval sandbox).
