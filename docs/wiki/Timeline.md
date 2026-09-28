# Timeline

All times Europe/Sofia. Model = Qwen 3.8 via vLLM + LiteLLM unless stated.

| When | What | Outcome |
|---|---|---|
| 26 Sept | **Batch 1**: opencode, pibox, Claude Agent SDK on the retry/backoff task, thinking on, agents on the host | opencode 2/2, pibox 2/2, SDK 0/2 (timeouts, API errors) |
| 26 Sept | An Agent SDK run escaped its folder and edited a real repo (reverted) | From here on every run is in a container that mounts only its repo copy |
| 26–27 Sept | **Batch 2**: Qwen vs Gemma | Qwen 5/6, Gemma 0/3 |
| 27 Sept | Gateway routing fix; **batch 3**: thinking off vs on | Thinking off 3–4× faster, same pass rate; thinking off from here on |
| 27 Sept | **Batch 4**: Copilot CLI, Qwen Code, opencode, **mini v1** in containers | All pass except one mini v1 run (12/14) |
| 27 Sept | Three new tasks (T1 real bug, T2 multi-file feature, T6 safety traps); bases pruned after a fix leaked through git history | |
| 27–28 Sept | **Batch 5**: opencode, Copilot CLI, pibox, Aider, Hermes, then mini v1, × 3 tasks × 3 | mini v1, opencode, Hermes 9/9; pibox 8/9; Copilot, Aider 6/9; 0 traps followed |
| 28 Sept | Grader bug (file names with spaces) found and fixed; all runs regraded, one flipped to PASS | |
| 27 Sept 23:30 | **mini v2** written from a spec (pi-parity tools), 26 tests | |
| 28 Sept 01:30 | Host crash wiped the working folder; trial kit rebuilt from the session log and verified with `selfcheck.sh` | |
| 28 Sept 08:25–10:33 | **Batch 6**: mini v2 × 3 tasks × 3; two runs rerun after a gateway restart | 9/9, no measurable gain over v1 |
| 28 Sept 11:00–11:40 | **mini in TypeScript** (npm package with a Docker sandbox); published as `@marinski/mini` 0.2.0, then 0.2.1 by the tag-driven release workflow | 28 tests; 300-case parity check against Python |
| 28 Sept 11:22–12:36 | **Batch 7**: the TypeScript bundle × 3 tasks × 3 | 9/9, like v2 |
| 28 Sept 12:37–12:50 | **mini v3** (TypeScript): a workspace-fingerprint loop breaker (nudge at 8 idle tool calls, firmer at 16), a requirement-checklist prompt, retries up to 3 minutes; 34 tests | |
| 28 Sept 12:50–13:54 | **Batch 8**: the v3 bundle × 3 tasks × 3 | 8/9; calls 18% and tokens 14% below batch 7; the one failure was a `refunds`/`refunds_eur` column-key slip, not the loop breaker |
| 28 Sept | `@marinski/mini` **0.3.0** released: npm package + GitHub release via the tag workflow | |
