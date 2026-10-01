> Implementation spec for the next trial round, written 28 Sept 2026 after batch 8 (mini v3,
> loop breaker) published as `@marinski/mini` 0.3.0. The trial kit is in
> `~/repos/agentpipe-mini-v2/harness/trial/` (worktree of `~/repos/agentpipe`); harness code in
> `~/repos/mini` (`src/`). Answers to the first round of questions are recorded at the end.

# Batch 9: harder tasks, and a lighter nudge

## Goal

Make the pass rates actually separate the harnesses, and confirm the loop breaker's gain is not
bought with false-positive nudges.

Two pieces of work, in order:

- **A. Harder tasks (T7, T8, T9).** T1/T2/T6 are exhausted: mini v3, opencode and Hermes all clear
  them, so only time and tokens differ. Add three tasks that can fail for a strong harness, and
  re-baseline the field on them.
- **B. Nudge tuning.** Batch 8 showed a real gain over batch 7 (−18% calls, −14% tokens), but the
  nudge fired only on T1 runs, and `mini3-t1-2` still took 67 calls. Decide from the transcripts
  whether the trigger should be later or two-strike, and measure the winner; ship the code change
  as **0.3.1**.

Context management is **not** in this round (no run has passed ~42k prompt tokens). The t2-2
`refunds`/`refunds_eur` slip is model variance and gets no harness change.

## Evidence behind the scope

| Evidence | Consequence |
|---|---|
| Batch 8 geometry: mini v3 8/9 (T1 3/3, T2 2/3, T6 3/3) on a field where opencode is 16/16 and Hermes 9/9. | The current three tasks have a ceiling; new tasks are the only way pass rate becomes a signal. |
| The one failure (t2-2) was a single wrong CSV column key, in no other run. | Not a harness defect; do not chase it. |
| v3 vs the same bundle at 0.2.x (batch 7 → 8): calls 275 → 226, tokens 3.96M → 3.42M, T2 tokens −39%, no run hit the 60-step cap. | Keep the loop breaker; tune the trigger, don't remove it. |
| Nudges fired only in `mini3-t1-1` (2, ~steps 25/33) and `mini3-t1-2` (3); t1-2 still reached 67 calls / 15.8 min. | The "soft at 8, strong at 16" trigger is too late on the run that needs it most. |
| `Progress` already takes `after` from `MINI_NUDGE_AFTER` (default 8; 0 = off). | `after` variants need no code — run them with an env var first. |
| Peak prompt across batches ≈ 42k. | No compaction now; revisit after Part A. |
| support-pipeline `81e0277` fixed data loss from a truncated extraction reply (`build_faq.py` + `llm.py` + tests). | T7's reproduce-first bug. |
| mt-backtest-manager is 1,391 files of TypeScript (Next.js backend + frontend, vitest unit tests, Playwright e2e). | T8's larger-repo, multi-file, Node task. |
| agentpipe is a 96-file Python pipeline with pure parser code and pytest, and a real fix history. | T9's deeper Python fix, offline-testable. |

## Decisions

| Topic | Decision (from the 28 Sept answers) |
|---|---|
| Task set | Add **T7, T8, T9**; keep T1/T2/T6 unchanged. |
| **T7** | `support-pipeline` at `81e0277^` (truncated extraction reply; reproduce then fix). |
| **T8** | `~/apps/mt-backtest-manager` — the frontend slice of `6d4cb6c` (`useFitPopoverToViewport` hook + `LibraryBrowser` integration + vitest), a larger-repo multi-file TypeScript task. |
| **T9** | `~/repos/agentpipe` at `7e025f3^` — the qa-gate parser fix (rejects skipped/delegated phases) in `findings_parse.py` + tests; pure Python, DB-free. |
| Reps | **3 per task** for the batch-9 baseline. |
| Field | **mini v3, opencode, pibox, Hermes.** |
| Nudge variants | Control (`after=8`) plus the single value B0 points at. |
| Two-strike | **Build it**: add a repetition-based trigger to `progress.ts` with unit tests; release 0.3.1 only if it wins. |
| Traps | Only T6 carries planted-instruction traps. |
| Context management | Out of scope unless a batch-9 run passes ~60k prompt tokens. |
| t2-2 slip | No change. |
| Node deps (T8) | `setup.sh` runs `npm ci` once on the host into `$TRIAL_DATA/deps/t8/node_modules`; `run_trial.sh` mounts it read-only. No new image. |
| Bases | From the real repos via `setup.sh`'s `base()` + `prune()` (single commit, no remotes/tags/reflog). |

## Part A — harder tasks

### What makes a task "harder"

A task earns its place only if it does at least one of:

1. **Needs a reproduction before a fix** — the failure is conditional (truncation, boundary,
   ordering), so the agent must build the failing case rather than pattern-match.
2. **Touches more files/layers** — the change spans several modules, so the agent must find call
   sites and keep them consistent.
3. **Runs in a larger repo** — locating the code among many files is itself the work.

### Candidate tasks

| Task | Repo (base) | What the prompt asks | Why it's harder | How it's graded |
|---|---|---|---|---|
| **T7** reproduce-first bug | `support-pipeline` at `81e0277^` | "Extraction silently drops part of a chunk when the model's reply is truncated; make it not lose data." | Conditional bug; the failing input is not given; fix spans `build_faq.py` and `llm.py`. | Hidden truncation fixture + regression on `tests/test_build_faq.py`, `tests/test_llm_gateway_auth.py` (pytest). |
| **T8** larger-repo multi-file | `mt-backtest-manager` at `6d4cb6c^` | "Make the library browser's popovers fit the viewport: add a reusable fitting hook and use it in the browser." | 1,391-file repo; backend/frontend split; a new hook wired into an existing component. | `vitest --run` on `frontend`'s hook + component tests (mocked, offline). |
| **T9** deeper Python fix | `agentpipe` at `7e025f3^` | "The qa gate accepts a report that skipped or delegated phases; require real Phase headings and reject skipped/delegated phases." | Conditional parsing bug; needs a reproduction; touches the parser's phase logic. | pytest on `tests/test_findings_parse.py` (pure, DB-free). |

The exact prompt for each is finalised in Step 3, after the hidden tests exist, so it names only
what the tests check.

### Kit extensions this round requires

The kit is Python/pytest today; two tasks need new plumbing:

- **Node task support (T8).** The image is already `node:24-bookworm-slim`, but a clone has no
  `node_modules` and the container has no network. `setup.sh` runs `frontend/`'s `npm ci` **once on
  the host** into `$TRIAL_DATA/deps/t8/node_modules`, and `run_trial.sh` mounts it **read-only** at
  `/work/frontend/node_modules` (nested bind inside `/work`). The grader runs
  `node_modules/.bin/vitest --run` in `frontend/`. Verify the mounted dir is not written.
- **agentpipe venv (T9).** `tests/conftest.py` imports `agentpipe_runner.db`, which imports
  `psycopg`; add `psycopg[binary]` and `python-dotenv` to `$TRIAL_DATA/venv` (harmless to the other
  tasks) so collection works without a database.
- **Submodules.** `mt-backtest-manager` has two submodules under `docker/`; confirm the T8 package
  tests run without them, or vendor what is needed into the base.

## Part B — nudge tuning

### Step B0: measure before changing

From batch 6/7/8 transcripts (`~/agent-trials/batchN/logs/mini*.jsonl`), per run compute:

- the **longest idle run** (consecutive tool calls with no file change, `progress.ts`'s
  definition) and where it sat;
- whether a nudge fired, at which step, and the calls/tokens that followed it;
- for capped runs, the idle-run length at the cap.

Classify runs **looping** (idle run ≥ 12, or ends at the cap) vs **healthy**. **Working when:** a
table separates the classes and names the smallest `after` that fires on looping runs without
touching healthy ones — the single variant Part B will test against the control.

### Step B1: the two-strike trigger (code, 0.3.1)

Add a repetition-based trigger to `src/progress.ts`, behind `MINI_NUDGE` (e.g. `after` = today's
behaviour; `strike` = nudge when the same tool + arguments repeats N times, or two consecutive
idle windows, whichever B0 supports). Keep the existing `MINI_NUDGE_AFTER` semantics for `after`.

**Working when:** unit tests in `test/` cover the new mode (fires on repetition, silent on healthy
progress, still respects `after=0`), `npm test` and `npm run typecheck` pass, and the bundle is
otherwise unchanged.

### Step B2: the A/B

On **T1** plus the Part A task that loops most, run: control (`after=8`, current bundle) vs the
B0-picked `after` value vs the two-strike mode. Compare per variant: passes, median calls, median
tokens in, total calls/tokens, and **loop-tail cost** (calls/tokens after the first nudge). A
variant wins if it holds passes and cuts loop-tail cost with no rise in nudges on healthy runs.

Do not change the shipped default until the A/B has a winner; if none beats the control, keep
`after=8` and say so.

## Part C — context-management gate

After Parts A and B, read the peak `prompt_tokens` across every batch-9/10 run.

- If any run exceeds **~60k**, open a compaction item with that run as the fixture.
- Otherwise record "no compaction needed" in the roadmap.

No code is written for this in the current round.

## Steps

### Step 1: Mine the nudge data (no model calls)

Produce the idle-run table from B0.

**Working when:** the table separates looping from healthy runs, names the single `after` variant
and whether a two-strike trigger is warranted, and is saved under `docs/`.

### Step 2: Extend the kit (no model calls)

Node task support, the agentpipe venv deps, and submodule handling as above.

**Working when:** a throwaway vitest package runs offline in the container with the mounted
`node_modules`, and `pytest --collect-only` for the chosen agentpipe test files succeeds in
`$TRIAL_DATA/venv` with no database. No network is attempted in-container.

### Step 3: Build the three tasks (no model calls)

T7 first, then T8, then T9 — one at a time — each with `TASK.md`, hidden tests, and `reference.sh`;
wire `grade.py`, `setup.sh`, `run_trial.sh`, `selfcheck.sh`.

**Working when:** for each task, `selfcheck.sh` shows the unchanged base FAILing, the reference
PASSing, out-of-scope = 0, commits = 0, and the regression count equals the base's measured
old-test count.

### Step 4: Finalise each prompt against its tests

Write `TASK.md` last, naming only what the hidden tests check, then re-run selfcheck.

**Working when:** the reference still passes and a deliberately off-spec solution still fails.

### Step 5: Difficulty gate (model calls; one task at a time)

Run `opencode`, `Hermes`, `pibox` and `mini3` once on each new task, sequentially via `queue.sh`.

**Working when:** each task is **kept** (a strong harness fails, or the median cost is ≥2× the
cheapest) or **re-scoped** back to Step 3. Only kept tasks advance. (Question N2: widen the field
here only if the four don't separate.)

### Step 6: Baseline batch 9

Queue the kept tasks × **3 reps** × the four harnesses.

**Working when:** `summarize.py` reports every run graded, no out-of-scope files, and no vLLM
restart mid-run (or it is noted).

### Step 7: Nudge A/B (batch 10)

Run Step B2's variants on T1 plus the looping new task.

**Working when:** each variant has the same run count on the same tasks, and the report states the
winner (or that the control held) with the loop-tail numbers.

### Step 8: Write up and publish

`results/batch-9.*` and `results/batch-10.*`, new wiki `Results-Batch-9` / `Results-Batch-10`,
update `Results.md`, `Timeline.md`, `Home.md`, `Roadmap.md`, README. If a nudge change wins,
`CHANGELOG.md` `0.3.1`, `npm version patch`, `git push --follow-tags`.

**Working when:** the wiki and repo match the data, the combined Results page includes the new
batches, and no secrets or private repo content are published.

## How we'll judge it

- **Part A:** hidden-test pass rate per task (now the primary signal), plus median calls/tokens/time;
  a task that separates the field is the deliverable.
- **Part B:** passes held, loop-tail calls/tokens cut, nudges-on-healthy-runs not increased.
- **Must hold:** traps = 0, out-of-scope = 0, commits = 0, runs never overlap on Qwen.
- **Caveat:** with 3 reps, only large differences are evidence; the nudge variant changes only the
  trigger (not tools or model), so that comparison is clean.

## Questions

### Answered 28 Sept 2026

1. **Task count/repos →** T7 support-pipeline; **T8 `~/apps/mt-backtest-manager`**; **T9
   `~/repos/agentpipe`**.
2. **Field width →** mini v3, opencode, pibox, Hermes.
3. **Reps →** 3 per task.
4. **Nudge variants →** control + the one B0 points at.
5. **Two-strike →** build it now (0.3.1).
6. **T9 shape →** real feature/fix, not synthetic.
7. **New-task traps →** keep traps only in T6.
8. **Placement →** keep `docs/SPEC-batch9.md` beside `docs/SPEC-v2.md`.
9. **T9 fix →** `7e025f3` (qa gate rejects skipped/delegated phases), base `7e025f3^`.
10. **T8 scope →** the `6d4cb6c` frontend slice (`useFitPopoverToViewport` + `LibraryBrowser`), base
    `6d4cb6c^`.
11. **Node deps →** preinstall on the host, mount `node_modules` read-only (no new image).
12. **Committing the spec →** leave uncommitted for now.

All questions are resolved; no open items.

## Build status (this pass)

**Done (no model calls):**

- **T8 and T9 built and wired** — `tasks/tN/{TASK.md, hidden tests, reference.sh}`; `grade.py`,
  `setup.sh`, `run_trial.sh` and `summarize.py` extended. `selfcheck.sh` is green: each unchanged
  base FAILs, each reference PASSes (t8 3/3 hidden with 21 regressions, t9 5/5 hidden with 29
  regressions). T9's count is 5, not the 4 originally planned: the hidden test is the real fix
  commit's own `tests/test_findings_parse.py` (`7e025f3`), which has five cases, and the unchanged
  base passes one of them.
- **T7 is not built.** Its assets lived uncommitted in the `~/repos/agentpipe-mini-v2` worktree, which
  is gone (git still lists it as prunable), so nothing can be copied back. It is also out of scope for
  the context-plugins trial (`docs/SPEC-context-plugins.md`, step 1). To rebuild it: base
  `content-pipeline` at `81e0277^`, hidden truncation fixture for `build_faq.py` plus the
  `tests/test_build_faq.py` and `tests/test_llm_gateway_auth.py` regressions, target 3/3 with 63
  regressions holding, reference = the real `81e0277` diff.
- **Kit extensions** — `setup.sh` builds the three bases, adds `psycopg[binary]` + `python-dotenv`
  to the grading venv, and preinstalls T8's `frontend/node_modules` into `$TRIAL_DATA/deps/t8`.
  `run_trial.sh` mounts it read-only at `/work/frontend/node_modules`; vitest needs `--no-cache`
  (its results cache writes into `node_modules/.vite`, which is read-only).
- **Two-strike trigger** — `src/progress.ts` gained `MINI_NUDGE=after|strike` (+ `MINI_NUDGE_STRIKE`,
  default 3); `src/agent.ts`/`src/cli.ts` plumb it. `npm run typecheck` and `npm test` (37 tests) pass.

**Pending (needs Qwen or a calibration run):**

- **B0 calibration.** The transcripts log each tool call's name and result but **not its arguments**,
  so the *strike* threshold and the winning `after` value can only be calibrated from a run that
  records repeats — deferred to the A/B pre-step. Current defaults (`after=8`, `strike=3`) stand.
- Steps 5–8: difficulty gate, batch 9 baseline, nudge A/B, write-up and any 0.3.1 release.

