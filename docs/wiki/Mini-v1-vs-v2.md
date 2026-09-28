# Mini v1 vs v2

## What v2 changes

| | v1 | v2 |
|---|---|---|
| **edit** | One `old`/`new` replacement; returns `ok`. | `edits[]`: several replacements in one file per call, all matched against the original file; overlapping, empty, malformed or non-unique edits are rejected with an error naming the edit, and nothing is written. Returns `ok` plus a unified diff (3 context lines, cut at 1500 characters). Still accepts v1's `old`/`new`, and `edits` sent as a JSON string or a single object. |
| **read** | 400 lines; anything over 20k characters loses its middle, with no hint. | Up to 2000 whole lines within 20k characters, then `[more: N lines left; continue with offset=K]`. A `limit` above 2000 is clamped; an offset past the end is an error; a single line over 20k characters is cut and marked. |
| **bash output** | First and last 10k characters, cut mid-line. | Within 20k characters (including the `exit N` line): up to the first 50 lines within 5k characters, `...[cut N lines]...`, then as many whole last lines as fit, so both the top grep hits and the pytest summary survive. A line too long to fit keeps its start or end, marked with `…`. |
| **prompt** | Two sentences. | Tool list plus guidance: explore with bash (ls, rg, find), edit tips, minimal changes, run the tests before finishing. |
| **transport retry** | OpenAI SDK, 2 retries (about 1.5 s). | 6 retries (about 23 s), enough to ride out a gateway restart. |
| **model-call failure** | Traceback; the transcript has no cause. | Logged as `{"stopped": "api error: ..."}`; exit code 1. |
| **transcript** | No token counts. | Each step logs `prompt_tokens`. |

The 20k-character cap per tool result stays on purpose: v2 has no compaction, and pi's larger
limit (50 KB) is only safe because pi compacts old turns.


## v1 vs v2

| | v1 (batch 5) | v2 (batch 6) |
|---|---|---|
| Passed | 9/9 | 9/9 |
| Median time | 6.5 min | 9.5 min |
| Median calls | 23 | 20 |
| Median tokens in | 273k | 272k |
| Total time | 60 min | 76 min |
| Total calls | 222 | 222 |
| Total tokens in | 2.53M | 3.80M |

| Task (sum of 3) | v1: time / calls / tokens in | v2: time / calls / tokens in |
|---|---|---|
| T1 | 21 min / 96 / 1.34M | 27 min / 90 / 1.54M |
| T2 | 27 min / 71 / 0.91M | 36 min / 92 / 2.01M |
| T6 | 11 min / 55 / 0.28M | 14 min / 40 / 0.26M |

**Reading:** nearly all of v2's extra cost is two runs (t1-3, and t2-1 which reran its own
failing test ~15 times). The other seven are at or under v1's typical cost. v2's new tool
behaviour barely fired: 1 read-continuation hint and 0 output cuts in ~150 tool calls, so on these
tasks the tool changes neither helped nor hurt. Run-to-run variance in how long the model loops on
its own tests dominates; with 9 runs each, no difference here is evidence.

## And the TypeScript port

See [[Results Batch 7]]: 9/9, median 8.4 min and 309k tokens in, within v2's spread.
