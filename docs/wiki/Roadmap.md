# Roadmap

## What the trials say so far

1. **The tasks are too easy to separate the good harnesses.** mini v1, mini v2, opencode and
   Hermes all went 9/9. Differences show up only in time and tokens, and those are dominated by
   run-to-run variance (one looping run can triple a task's total).
2. **Tool polish didn't matter here.** v2's paged reads and line-aware cuts almost never fired.
3. **What does cost time is self-test loops:** the model rerunning its own failing test many
   times. That's the next thing worth attacking.
4. **Retries must survive a gateway restart.** v2's ~20 s of retries didn't; two runs died at
   step 0.

## Next steps, in order

1. **Harder tasks** so pass rates can differ: longer multi-file features, a bug needing a
   reproduction first, a task over a larger repo (context pressure, where compaction matters).
   Keep the private-repo setup, 3–5 runs per task.
2. **Loop breaker experiment (v3):** a short requirement checklist in the prompt, and a nudge
   when the same test command fails 3 times in a row ("re-read the spec, change approach").
   Measure calls and tokens against v1/v2 on the same tasks.
3. **Robust transport:** retry connection errors and 5xx for up to ~2 minutes with backoff.
4. **Context management** only if the harder tasks push prompts past ~60k tokens (none did yet:
   peak 42k).
5. ~~Packaging~~ done: `@marinski/mini` on npm, released by pushing a version tag (batch 7
   confirmed the TypeScript port matches v2).

## Packaging mini for npm (like opencode, pi, Copilot CLI)

Those agents are Node CLIs published to npm with a `bin` entry, so `npm i -g <pkg>` puts a
command on your PATH. mini is Python today, so there are two routes:

| Route | How | Pros | Cons |
|---|---|---|---|
| **A. Port to TypeScript** (recommended) | ~250 lines with the `openai` npm SDK and `child_process`; `package.json` with `"bin": {"mini": "dist/cli.js"}`; `npm publish --access public` as a scoped package (`mini` itself is taken on npm) | One runtime like the others; `npx @scope/mini "task"` just works | A rewrite; re-run the trials to prove parity |
| B. npm wrapper around Python | A small Node `bin` that runs `uvx`/`python3` on the bundled `.py` | Keeps the tested Python | Needs Python + `openai` on the machine; two runtimes |
| (C. Python tool) | `pyproject.toml` with a `[project.scripts] mini = ...` entry; `uv tool install` / `pipx install` | Easiest, no rewrite | Not npm |

Whatever the route, the CLI should **sandbox itself by default**: run in a container that mounts
only the current folder (refuse `/` and `$HOME`), with a `--no-sandbox` opt-out. An unattended
agent escaped its folder once during these trials.

Planned CLI shape:

```text
mini "task"                       # run in ./ inside a container
mini --model qwen --base-url http://host:4000/v1 "task"
MINI_API_KEY=... mini -p "task"   # key from env or a key file, never a flag
```
