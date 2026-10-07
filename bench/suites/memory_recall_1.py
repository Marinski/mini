"""memory_recall_1: verbatim recall of function bodies after the opening brace.

Our design (Protorikis's prompt text is not exposed): 16 functions are picked
evenly from pinned three.js. Each prompt shows the source up to and including
the opening brace — preceded by ``fraction`` of the file as context — and asks
for the body lines. The four profiles grow that context:

    eighths  8 jobs x 2 prompts   (1/8 of the file)
    quarters 4 jobs x 4 prompts   (1/4)
    halves   2 jobs x 8 prompts   (1/2)
    full     1 job  x 16 prompts  (the whole file)

The check: the first 8 body lines exactly (whitespace-insensitive), no missing
or extra lines, and at most 100 output lines.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, ClassVar

from bench import code_context
from bench.code_context import require_lines
from bench.suites import checks
from bench.suites.base import FAIL, PASS, Check, Job, Prompt, Suite

PROFILE_JOBS = {"eighths": 8, "quarters": 4, "halves": 2, "full": 1}
PROFILE_FRACTION = {"eighths": 1 / 8, "quarters": 1 / 4, "halves": 1 / 2, "full": 1.0}
RECALLS = 16
MAX_OUTPUT_LINES = 100
FIRST_LINES = 8


def _select(functions: list[dict], count: int) -> list[dict]:
    if len(functions) <= count:
        return functions
    step = len(functions) / count
    return [functions[int(i * step)] for i in range(count)]


def _prompt(name: str, context: str) -> str:
    return (
        "Here is an excerpt of the three.js source. It ends at the opening "
        f"brace of the function `{name}`:\n\n```javascript\n{context}\n```\n\n"
        "Reproduce the function body exactly — the lines that come after the "
        "opening brace — up to 80 lines. Output only those lines, with no code "
        "fences and no explanation."
    )


class MemoryRecall1(Suite):
    id = "memory_recall_1"
    profiles = ("eighths", "quarters", "halves", "full")
    default_params: ClassVar[dict[str, Any]] = {"multi_turn": False}

    def build(self, profile, ctx):
        if profile not in PROFILE_JOBS:
            raise ValueError(f"unknown profile {profile!r}; have {', '.join(self.profiles)}")
        lines = require_lines(ctx)
        functions = _select(code_context.find_functions(lines), RECALLS)
        preceding = max(20, int(PROFILE_FRACTION[profile] * len(lines)))
        jobs = []
        jobs_count = PROFILE_JOBS[profile]
        per_job = RECALLS // jobs_count
        for j in range(jobs_count):
            group = functions[j * per_job : (j + 1) * per_job]
            prompts = [
                Prompt(
                    fn["name"],
                    _prompt(
                        fn["name"],
                        code_context.context_window(lines, fn["brace_index"], preceding),
                    ),
                )
                for fn in group
            ]
            jobs.append(
                Job(
                    id=f"{profile}-{j + 1}",
                    prompts=prompts,
                    params=dict(self.default_params),
                    meta={"expected": [fn["body"] for fn in group]},
                )
            )
        return jobs

    def check(self, job, subjobs):
        expected = job.meta["expected"]
        return [
            body_check(sub.response, expected[i]) for i, sub in enumerate(subjobs)
        ]


def body_check(output: str, expected_body: list[str]) -> Check:
    got = checks.code_lines(output)
    if len(got) > MAX_OUTPUT_LINES:
        return Check(FAIL, f"{len(got)} output lines > {MAX_OUTPUT_LINES}")
    expected = [line.rstrip() for line in expected_body][:MAX_OUTPUT_LINES]
    while expected and not expected[0].strip():
        expected.pop(0)
    while expected and not expected[-1].strip():
        expected.pop()
    got_stripped = [line.strip() for line in got]
    expected_stripped = [line.strip() for line in expected]

    for i in range(min(FIRST_LINES, len(expected_stripped))):
        if i >= len(got_stripped) or got_stripped[i] != expected_stripped[i]:
            return Check(FAIL, f"line {i + 1} of the first {FIRST_LINES} differs")

    missing = Counter(expected_stripped) - Counter(got_stripped)
    extra = Counter(got_stripped) - Counter(expected_stripped)
    missing.pop("", None)
    extra.pop("", None)
    if missing:
        return Check(FAIL, f"{sum(missing.values())} missing line(s)")
    if extra:
        return Check(FAIL, f"{sum(extra.values())} extra line(s)")
    return Check(PASS)
