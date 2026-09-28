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
| `src/`, `test/` | **mini in TypeScript** (the npm package): a port of v2, same tools, prompt, limits and transcript. `npm test`: 28 tests. `npm run build` bundles it into one file, `dist/mini.js`. |
| `mini_harness.py` | **v1** (Python): 86 lines. |
| `mini_harness_v2.py` | **v2** (Python): v1 plus pi-style tool behaviour (multi-edit with diff, paged reads, line-aware output cuts, retries). `test_mini_v2.py`: 26 tests. |
| `trial/` | The bench: containers, freeze guard, grader, batch queue, report. Task repos are private. |
| `results/` | Every batch: per-run pass/fail, time, calls, tokens. |
| `docs/` | v2 spec; `docs/wiki/` mirrors the wiki. |

## Headline (batch 5 + 6, 3 tasks × 3 runs, Qwen thinking off)

| Harness | Passed | Median time | Median tokens in |
|---|---|---|---|
| **mini v1** | **9/9** | **6.5 min** | 273k |
| mini v2 | 9/9 | 9.5 min | 272k |
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
