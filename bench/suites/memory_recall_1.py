"""memory_recall_1: verbatim recall of function bodies from code in the context.

Our design (Protorikis's prompt text is not exposed; its shapes are): pinned
three.js is split into equal chunks, one per job, and the job's functions are
picked from inside its chunk. Each prompt shows the whole chunk, then the 20
lines of one function up to its opening brace, and asks for the lines that
follow — so the body is in the context and the test is long-context retrieval,
not memorisation (a first version showed only the code before the brace, which
the model could only recite from training; corrected 7 Oct 2026). Prompts in a
job share the chunk as their prefix. The four profiles:

    eighths  8 jobs x 2 prompts   (1/8 of the file each, ~150 KB)
    quarters 4 jobs x 4 prompts   (1/4)
    halves   2 jobs x 8 prompts   (1/2)
    full     1 job  x 16 prompts  (the whole file)

The check (Protorikis's): the output is compared with the file's next 100 lines
after the brace — the first 8 exactly (whitespace-insensitive), no missing or
extra lines in the span written, and at most 100 output lines.
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


ANCHOR_LINES = 20


def _byte_chunks(lines: list[str], count: int) -> list[tuple[int, int]]:
    """Split ``lines`` into ``count`` contiguous (start, end) ranges of near-equal bytes."""
    total = sum(len(line) + 1 for line in lines)
    bounds, start, size, j = [], 0, 0, 1
    for i, line in enumerate(lines):
        size += len(line) + 1
        if j < count and size >= total * j / count:
            bounds.append((start, i + 1))
            start, j = i + 1, j + 1
    bounds.append((start, len(lines)))
    return bounds


def _prompt(name: str, chunk: str, anchor: str) -> str:
    return (
        "Here is an excerpt of the three.js source:\n\n"
        f"```javascript\n{chunk}\n```\n\n"
        f"In that excerpt, the function `{name}` begins like this, ending at its "
        f"opening brace:\n\n```javascript\n{anchor}\n```\n\n"
        "Continue it exactly as it is written in the excerpt: output the lines that "
        "come after the opening brace, up to and including the function's closing "
        "brace, then stop. Output only those lines, with no code fences and no "
        "explanation."
    )


class MemoryRecall1(Suite):
    id = "memory_recall_1"
    profiles = ("eighths", "quarters", "halves", "full")
    # As Protorikis sends it (7 Oct 2026).
    default_params: ClassVar[dict[str, Any]] = {"multi_turn": False, "thinking": False, "temperature": 0.0}

    def build(self, profile, ctx):
        if profile not in PROFILE_JOBS:
            raise ValueError(f"unknown profile {profile!r}; have {', '.join(self.profiles)}")
        lines = require_lines(ctx)
        functions = code_context.find_functions(lines)
        jobs_count = PROFILE_JOBS[profile]
        per_job = RECALLS // jobs_count
        bounds = _byte_chunks(lines, jobs_count)
        jobs = []
        for j, (start, end) in enumerate(bounds):
            inside = [
                fn for fn in functions
                if fn["decl_index"] >= start and fn["brace_index"] + len(fn["body"]) + 1 < end
            ]
            group = _select(inside, per_job)
            chunk = "\n".join(lines[start:end])
            prompts = [
                Prompt(
                    fn["name"],
                    _prompt(
                        fn["name"],
                        chunk,
                        "\n".join(lines[max(start, fn["brace_index"] - ANCHOR_LINES + 1) : fn["brace_index"] + 1]),
                    ),
                )
                for fn in group
            ]
            jobs.append(
                Job(
                    id=f"{profile}-{j + 1}",
                    prompts=prompts,
                    params=dict(self.default_params),
                    # Protorikis compares against the file's continuation, not the function
                    # alone: a 20-line window plus up to 80 lines after the brace.
                    meta={
                        "expected": [
                            lines[fn["brace_index"] + 1 : fn["brace_index"] + 1 + MAX_OUTPUT_LINES]
                            for fn in group
                        ],
                        # A body shorter than 8 lines needs only its lines and the closing brace.
                        "required": [
                            min(FIRST_LINES, sum(1 for line in fn["body"] if line.strip()) + 1)
                            for fn in group
                        ],
                    },
                )
            )
        return jobs

    def check(self, job, subjobs):
        expected = job.meta["expected"]
        required = job.meta.get("required") or [FIRST_LINES] * len(expected)
        return [
            body_check(sub.response, expected[i], required[i]) for i, sub in enumerate(subjobs)
        ]


def body_check(output: str, expected_continuation: list[str], required: int = FIRST_LINES) -> Check:
    """Pass: the first 8 lines exact, and no missing or extra lines in the span the model wrote.

    ``expected_continuation`` is the file after the opening brace (up to 100 lines), so a
    model that finishes the body and carries on into the next function is not penalised
    for lines that really follow in the file (as Protorikis grades it).
    """
    got = [line.strip() for line in checks.code_lines(output)]
    if len(got) > MAX_OUTPUT_LINES:
        return Check(FAIL, f"{len(got)} output lines > {MAX_OUTPUT_LINES}")
    expected = [line.strip() for line in expected_continuation[:MAX_OUTPUT_LINES]]
    got_nb = [line for line in got if line]
    expected_nb = [line for line in expected if line]

    for i in range(min(required, len(expected_nb))):
        if i >= len(got_nb) or got_nb[i] != expected_nb[i]:
            return Check(FAIL, f"line {i + 1} of the first {required} differs")

    span = expected_nb[: len(got_nb)]
    missing = Counter(span) - Counter(got_nb)
    extra = Counter(got_nb) - Counter(expected_nb)
    if missing:
        return Check(FAIL, f"{sum(missing.values())} missing line(s)")
    if extra:
        return Check(FAIL, f"{sum(extra.values())} extra line(s)")
    return Check(PASS)
