# mini wiki

**mini** is a minimal coding agent (bash / read / edit / write in one loop) and a test bench that
compares it with full coding-agent harnesses on a local model: Qwen 3.8 served by vLLM behind a
LiteLLM gateway. The question: *how much harness does a local model actually need?*

## Pages

- [[Timeline]]: everything that was run, in order
- [[Test Method]]: isolation, grading, what counts as a pass, how tokens are measured
- [[Tasks]]: what the agents were asked to do
- [[Results]]: every batch, every harness
- [[Mini v1 vs v2]]: the harness versions and how they compare
- [[Roadmap]]: what's next, and packaging mini for npm

## Headline so far (28 Sept 2026)

| Harness | Batch 5 (T1+T2+T6, 9 runs) | Median time | Median tokens in |
|---|---|---|---|
| **mini v1** (86 lines) | **9/9** | **6.5 min** | 273k |
| mini v2 (231 lines) | 9/9 (batch 6) | 9.5 min | 272k |
| mini, TypeScript (npm `@marinski/mini`) | 9/9 (batch 7) | 8.4 min | 309k |
| opencode | 9/9 | 10.8 min | 402k |
| Hermes Agent | 9/9 | 26.2 min | 1.66M |
| pibox (pi) | 8/9 | 6.9 min | 210k |
| Copilot CLI | 6/9 | 12.9 min | 691k |
| Aider | 6/9 | 18.8 min | 50k |

An 86-line loop matched the best full harnesses on these tasks. Adding pi's tool behaviour (v2)
changed nothing measurable: the new behaviour rarely triggered, and run-to-run variance in how long
the model loops on its own tests dominates. The TypeScript port (the npm package) matched v2:
9/9, with time and tokens inside v2's spread.

Install: `npm i -g @marinski/mini` (Node 20+, Docker).

Source: `mini_harness.py` (v1), `mini_harness_v2.py` (v2), `trial/` (the bench), `results/`.
