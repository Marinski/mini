> Design spec for v2, written while mini lived inside a private monorepo (`agentpipe/harness/mini/`); paths below refer to that layout. In this repo the harness is at the root.

# mini-harness v2: what v1 lacks, and how to close the gap

The trial kit this spec refers to (run_trial.sh, grading, tasks) is now in `../trial/`, rebuilt after the scratchpad was lost in the 28 Sept host crash; paths below that point at the old scratchpad `batch5/` folder map to `../trial/` and `$TRIAL_DATA`.

## Goal

Learn whether pi-style tool behaviour changes how our local Qwen (`vllm-qwen3.8-nothink`)
works, with the model, the four tools and the tasks held fixed. v2 is the 86-line
mini-harness (v1, `/opt/mini_harness.py` in the trial images) plus what pi does inside those
same four tools. It runs 9 times against v1's 9 on the batch 5 tasks.

This is for learning only: pibox and the other harnesses stay as they are, whatever v2 scores.

## What 9 against 9 can and can't show

- **Pass rate is descriptive, not the verdict.** 9/9 against 7/9 is within chance (Fisher's
  exact test, p≈0.47); only about 4 of 9 or more would mean something. And the best harnesses
  already sit at 7/7–7/8 on these tasks, so a ceiling is likely.
- **The main result is how the work was done**, compared task by task:
  - model calls, input tokens and wall time;
  - how often v2's new behaviour actually fired (multi-edit calls, reads with a continue hint,
    cut outputs);
  - peak prompt tokens per run.
- **The system prompt (D) can't be separated** from the other changes, since all changes are
  tested together (decision). The write-up must say so.

## Evidence behind the scope

| Evidence | Consequence |
|---|---|
| Mini v1's 30 tool calls in batch 4 returned **0 errors**: no failed edit, no cut-off output. Only 2 runs, on the easiest task. | Tolerant edit matching and CRLF handling are out, unless step 1 finds edit errors in v1's batch 5 runs (T2 is where Aider's edits failed). |
| No compaction fired and pi saw no cut-off reply in any of the 37 batch 5 runs (peak prompt 65k of 128k). | No compaction and no cut-off handling. So v2 keeps v1's **20k-character cap per tool result**: pi's 50 KB is only safe with compaction. |
| Mini never looped; its 60-step cap bounds every run. | No loop guard. |
| pi's only retries were 3, all from one gateway restart; it recovered after between 6 and 14 s. The OpenAI SDK in the image waits 0.5, 1, 2, 4, 8 s (8 s max, jitter up to 25% down). | `max_retries=6` (about 23 s) instead of v1's 2 (about 1.5 s). |
| Mini's only batch 4 failure was a **missed requirement** (502 not retried). | None of the changes targets that; see Question 1. |

My earlier claims that mini mainly lacks search tools, sub-agents and retries were wrong:
- **Search tools:** opencode used `grep` 7 times in 257 tool calls and Copilot 8 in 786, and pibox has no search tools yet leads.
- **Sub-agents and to-do lists:** no harness used them.
- **Context:** mini's batch 4 failure wasn't a context problem.

## What v2 changes

| # | Area | pi | mini v1 | v2 |
|---|---|---|---|---|
| A | **Edit** | `edits[]`: several replacements per call; returns a diff. | One replacement per call; returns `"ok"`. | `edits[]` (still accepts v1's `old`/`new`, and `edits` sent as a JSON string or single object). All matched against the original file; overlapping edits rejected; nothing written unless every edit applies. Returns `ok` plus a unified diff with 3 context lines, cut at 1500 characters. |
| B | **Read** | 2000 lines / 50 KB, then "continue with offset". | 400 lines; `clip()` cuts the middle out of anything over 20k characters, with no hint. | Up to 2000 whole lines within 20k characters, then `[more: N lines left; continue with offset=K]`. Skips `clip()`. |
| C | **Bash output** | Keeps the last 2000 lines / 50 KB (pi has separate grep/find tools). | First and last 10k characters, cut mid-line. | Within 20k characters: the first 50 lines (at most 5k characters), then `...[cut N lines]...`, then as many whole last lines as fit. Keeps the pytest summary *and* the top grep hits. Skips `clip()`. |
| D | **System prompt** | Tool list with one-line descriptions, plus tool guidance. | Two sentences. | Tool list, plus: explore with bash (ls, rg, find), edit tips, minimal changes, run the tests before finishing. |
| E | **Transport retry** | 3 retries, 2/4/8 s. | SDK `max_retries=2`. | SDK `max_retries=6`. |
| F | **API failure** | Reported in the event stream. | No `try` around the model call: a traceback, and the log has no cause. | A model-call error is logged to the transcript as `stopped: api error: …` (a context overflow shows up here) and the harness exits with code 1. |
| G | **Transcript** | Usage per message. | No token counts. | Each step logs `prompt_tokens`, for the peak-context figure. |

Unchanged, by decision: `temperature=0.7`, `max_tokens=8000`, `MAX_STEPS=60`, the time budget,
the transcript's other fields, the `mini-harness` key, and the 300 s bash timeout.

## Decisions

| Topic | Decision |
|---|---|
| Test design | All changes together, run **once**: 9 runs against v1. No one-at-a-time follow-up, no extra rounds. |
| Sampling | Keep v1's `temperature=0.7` and `max_tokens=8000`. |
| LiteLLM key | Reuse `mini-harness`; v1 and v2 runs never overlap, so tokens separate by time window. |
| Location | `~/repos/agentpipe/harness/mini/`. |
| Docker image | None. v2 is mounted read-only into `agent-trial:4` at run time. |
| Goal | Learning only. |

## Files (`~/repos/agentpipe/harness/mini/`)

| File | What |
|---|---|
| `mini_harness_v2.py` | The harness. `run_tool(name, args, work)` and `SYSTEM` can be imported for tests; the OpenAI client is created in `main()`. |
| `test_mini_v2.py` | Behaviour tests for the tools, the prompt and the main loop (with a fake client, so no network). |
| `README.md` | What it is, how to run it and its tests, what changed from v1, and later the v1 vs v2 result. |

The tests run in the trial image, which has `openai` and `pytest`:
`docker run --rm -v ~/repos/agentpipe/harness/mini:/src:ro -w /tmp agent-trial:4 python3 -m pytest -q -p no:cacheprovider /src`.
agentpipe's own `pytest` only collects `tests/`, so it doesn't see them.

## Steps

### Step 1: Build and test v2 (can happen now; no model calls)

**Status: done (27 Sept).**
- Branch `feat/mini-harness-v2`, commit 296fdaa.
- 231 lines; 26 tests pass in `agent-trial:4`; ruff is clean.
- Two review passes. All findings are fixed except one Low, kept as documented behaviour: when a very long line sits early in the output, only its start is shown, even if room is left.

Implement A–G and the tests.

**Working when:**
- `test_mini_v2.py` passes in the image. It covers:
  - **Edit:** two disjoint edits in one call, with the diff's line numbers correct for both;
    overlapping edits rejected and the file unchanged; not found and found twice each naming the
    edit, file unchanged; the v1 shape; `edits` as a JSON string and as a single object.
  - **Read:** 2000-line pages with a continue hint; the 20k-character cap stops at a whole line
    with the right `offset`; reading on from that offset; paths outside `WORK` refused.
  - **Bash:** short output untouched; long output keeps its first 50 lines, a cut note and its
    last line; a single huge line is still capped.
  - **Prompt:** it lists the four tools.
  - **Main loop:** a plain reply ends the run, and `prompt_tokens` is logged; a connection error
    is logged as `stopped: api error` with exit code 1.
- `ruff check harness/` passes, and agentpipe's own `pytest` is unchanged.

### Step 2: Read v1's baseline (after the 9 queued v1 runs)

**Status: done (28 Sept).**
- v1 passed 9/9, with 1 tool error in 178 calls and no output cut. That hit the gate.
- You chose to run v2 anyway, judged on efficiency only.
- The first attempt died in the host crash at 01:30 on 28 Sept.

For each v1 run, from `batch5/logs/mini-*.jsonl`:
- **every run:** calls, tokens and steps;
- **every failure:** classify the cause as edit didn't apply, output cut in the wrong place,
  missed requirement, out of steps or time, gateway error, or other.

Write this into `harness/mini/README.md`.

**Gate:** stop and report before step 3 if either of these holds:
- v1 passes 8 or more of 9: v2 can then only be judged on efficiency. Is that worth 9 runs?
- most v1 failures have causes that A–G don't touch, especially missed requirements (Question 1).

### Step 3: Smoke run

Add a `mini2` case to `batch5/run_trial.sh`: the `mini` case with an extra
`-v ~/repos/agentpipe/harness/mini/mini_harness_v2.py:/opt/mini_harness_v2.py:ro` and
`python3 /opt/mini_harness_v2.py`.
- Make the edit only when no `run_trial.sh` is running, since bash reads a running script from
  disk as it goes.
- Run it as `run_trial.sh mini2 t6 smoke`, then move its `logs/`, `runs/` and `out/` files to
  `batch5/rehearsal/`, so the report doesn't include it.

**Working when:** the run finishes and is graded, and the transcript shows `prompt_tokens` and
at least one edit returning a diff.

### Step 4: Nine runs

- In `batch5/summarize.py`, add `"mini2": "mini-harness"` to `ALIAS` and `mini2` to `HARN`.
- Queue T1, T2, T6 × 3 with a copy of `mini_runs.sh` whose wait pattern also covers `mini`, so
  v1 and v2 never overlap.
- Each run's `meta.json` also records vLLM's `process_start_time_seconds`, read from `/metrics`
  at the start and end of the run. A change means the server restarted in between.

**Working when:** the report has a `mini2` row with 9 graded runs, no out-of-scope files, no v2
window overlapping a v1 window, and the same vLLM start time throughout (or the differences
noted).

## How we'll judge it

- **Primary:** per task, v2 against v1 on median model calls, input tokens and wall time, plus
  how often A–C fired (from the transcripts).
- **Descriptive:** hidden-test pass rate. A difference under about 4 of 9 is not evidence.
- **Must hold:** T6 traps followed = 0, out-of-scope files = 0, commits = 0.
- **Write-up** in `harness/mini/README.md`: the table, peak prompt tokens, whether v1's failure
  causes recurred in v2, and the caveat that the prompt change can't be separated out.

## Questions

1. Mini's only known failure is a **missed requirement**, and nothing in A–G targets that. If
   step 2 shows v1 failing mostly on missed requirements, should v2 get the requirement
   checklist? That's one extra message before the run may finish: "list each requirement and
   where your diff or tests cover it", about 10 lines.
2. Should a frozen copy of v1 go into agentpipe as well? v1 stays available as
   `/opt/mini_harness.py` in the `agent-trial:4` image.
3. The trial kit (the Dockerfiles, `run_trial.sh`, `grade5.py`, `summarize.py` and the task
   folders) lives in this session's scratchpad and will be lost with it. Move it into
   `agentpipe/harness/` too?
