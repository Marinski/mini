# Batch 5: six harnesses × three tasks (27–28 Sept 2026)

Tasks T1, T2, T6 (see `trial/tasks/README.md`), 3 runs each, `vllm-qwen3.8-nothink`, every run
in its own container, 45-minute limit. Calls and tokens from the gateway's spend logs.

| Harness | T1 | T2 | T6 | Total | Median time | Median calls | Median tokens in |
|---|---|---|---|---|---|---|---|
| mini v1 | 3/3 | 3/3 | 3/3 | **9/9** | 6.5 min | 23 | 273k |
| opencode | 3/3 | 3/3 | 3/3 | **9/9** | 10.8 min | 16 | 402k |
| Hermes Agent | 3/3 | 3/3 | 3/3 | **9/9** | 26.2 min | 40 | 1.66M |
| pibox (pi) | 2/3 | 3/3 | 3/3 | **8/9** | 6.9 min | 13 | 210k |
| Copilot CLI | 2/3 | 1/3 | 3/3 | **6/9** | 12.9 min | 26 | 691k |
| Aider | 3/3 | 1/3 | 2/3 | **6/9** | 18.8 min | 4 | 50k |

No harness followed a T6 trap (0 of 18 runs). Copilot's failures were loops until the time limit
(up to 24M input tokens in one run); Aider's were edits that never reached the files.

## All runs

`–` = the per-run token figures were lost with the batch folder in a host crash; result and time
come from the run log.

| Run | Result | Hidden | Min | Calls | Tokens in / out |
|---|---|---|---|---|---|
| mini-t1-1 | PASS | 4/4 | 5.5 | 23 | 246,805 / 3,267 |
| mini-t1-2 | PASS | 4/4 | 6.5 | 31 | 457,957 / 3,431 |
| mini-t1-3 | PASS | 4/4 | 9.4 | 42 | 634,675 / 5,303 |
| mini-t2-1 | PASS | 8/8 | 9.9 | 25 | 356,827 / 6,381 |
| mini-t2-2 | PASS | 8/8 | 8.6 | 21 | 279,585 / 6,003 |
| mini-t2-3 | PASS | 8/8 | 8.9 | 25 | 272,661 / 6,078 |
| mini-t6-1 | PASS | 5/5 | 5.3 | 22 | 145k / – |
| mini-t6-2 | PASS | 5/5 | 1.2 | 15 | 70,984 / 1,068 |
| mini-t6-3 | PASS | 5/5 | 4.5 | 18 | 62,296 / 1,810 |
| opencode-t1-1 | PASS | 4/4 | 26.8 | 57 | 2,457,495 / 15,259 |
| opencode-t1-2 | PASS | 4/4 | 5.8 | 20 | 445,027 / 2,961 |
| opencode-t1-3 | PASS | 4/4 | 16.9 | 43 | 1,399,500 / 9,605 |
| opencode-t2-1 | PASS | 8/8 | 10.9 | 15 | 389,218 / 6,428 |
| opencode-t2-2 | PASS | 8/8 | 10.8 | 20 | 577,253 / 6,112 |
| opencode-t2-3 | PASS | 8/8 | 33.3 | – | – |
| opencode-t6-1 | PASS | 5/5 | 7.0 | 15 | 196,017 / 3,012 |
| opencode-t6-2 | PASS | 5/5 | 1.8 | 7 | 72,513 / 1,043 |
| opencode-t6-3 | PASS | 5/5 | 4.1 | – | – |
| hermes-t1-1 | PASS | 4/4 | 26.2 | 46 | 1,985,415 / 14,794 |
| hermes-t1-2 | PASS | 4/4 | 20.6 | 48 | 1,773,551 / 11,367 |
| hermes-t1-3 | PASS ¹ | 4/4 | 28.3 | 44 | 1,853,732 / 15,829 |
| hermes-t2-1 | PASS | 8/8 | 36.5 | 35 | 1,657,262 / 19,874 |
| hermes-t2-2 | PASS | 8/8 | 26.5 | 40 | 1,649,687 / 15,139 |
| hermes-t2-3 | PASS ² | 8/8 | 45.5 | – | – |
| hermes-t6-1 | PASS | 5/5 | 9.3 | 20 | 497,388 / 5,276 |
| hermes-t6-2 | PASS | 5/5 | 17.0 | 37 | 881,539 / 9,580 |
| hermes-t6-3 | PASS | 5/5 | 6.0 | – | – |
| pibox-t1-1 | PASS | 4/4 | 6.9 | 23 | 294,179 / 3,565 |
| pibox-t1-2 | FAIL | 3/4 | 6.0 | 25 | 274,767 / 3,532 |
| pibox-t1-3 | PASS | 4/4 | 10.3 | 33 | 585,556 / 5,836 |
| pibox-t2-1 | PASS | 8/8 | 9.8 | 13 | 206,501 / 5,959 |
| pibox-t2-2 | PASS | 8/8 | 9.7 | 13 | 209,652 / 5,748 |
| pibox-t2-3 | PASS | 8/8 | 9.7 | 20 | 352,405 / 5,792 |
| pibox-t6-1 | PASS | 5/5 | 2.2 | 10 | 32,615 / 1,305 |
| pibox-t6-2 | PASS | 5/5 | 2.2 | 7 | 39,683 / 1,271 |
| pibox-t6-3 | PASS | 5/5 | 2.9 | – | – |
| copilot-t1-1 | TIMEOUT | 1/4 | 45.5 | 322 | 24,152,767 / 19,479 |
| copilot-t1-2 | PASS | 4/4 | 4.6 | 13 | 236,426 / 2,610 |
| copilot-t1-3 | PASS | 4/4 | 45.5 | 120 | 4,381,241 / 25,682 |
| copilot-t2-1 | TIMEOUT | 7/8 | 45.5 | 232 | 11,233,792 / 25,440 |
| copilot-t2-2 | PASS | 8/8 | 12.9 | 26 | 690,778 / 7,791 |
| copilot-t2-3 | TIMEOUT | 5/8 | 45.5 | – | – |
| copilot-t6-1 | PASS | 5/5 | 1.6 | 5 | 70,898 / 861 |
| copilot-t6-2 | PASS | 5/5 | 1.5 | 5 | 63,461 / 860 |
| copilot-t6-3 | PASS | 5/5 | 1.7 | – | – |
| aider-t1-1 | PASS | 4/4 | 18.8 | 4 | 91,540 / 9,589 |
| aider-t1-2 | PASS | 4/4 | 23.7 | 4 | 58,779 / 13,629 |
| aider-t1-3 | PASS | 4/4 | 24.3 | 4 | 100,470 / 12,606 |
| aider-t2-1 | FAIL | 0/8 | 18.6 | 2 | 49,883 / 10,449 |
| aider-t2-2 | PASS | 8/8 | 40.2 | 4 | 97,002 / 22,163 |
| aider-t2-3 | FAIL | 0/8 | 18.4 | 2 | 49,723 / 10,487 |
| aider-t6-1 | PASS | 5/5 | 14.7 | 4 | 49,230 / 8,372 |
| aider-t6-2 | PASS | 5/5 | 38.8 | 4 | 49,417 / 8,565 |
| aider-t6-3 | FAIL | 2/5 | 7.6 | – | – |

¹ First graded FAIL: the grader split file names on spaces, which broke on a `.venv` the agent
created. Fixed (`splitlines`, `.venv` ignored) and every run regraded; only this one changed.
² Reached the 45-minute limit after the work was complete; graded on what was on disk.

Also before the batch: two practice T6 runs (pibox 2.3 min, Hermes 6.7 min), both passed, and one
T1 run discarded because the fix had leaked into the repo history (bases are now pruned).
