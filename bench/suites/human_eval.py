"""human_eval: 164 Python problems; signature and docstring in, body out.

The completion is appended to the prompt and the problem's own tests are run in
the sandbox (``bench/sandbox``): network off, CPU and memory capped, ten
seconds a problem. The suite checks nothing itself-per-problem; ``finalize``
evaluates the whole batch at once.
"""

from __future__ import annotations

from typing import Any, ClassVar

from bench import data, humaneval
from bench.suites.base import (
    ERROR,
    FAIL,
    PASS,
    SKIPPED,
    Check,
    Job,
    Prompt,
    SubJob,
    Suite,
)

INSTRUCTION = (
    "Complete the following Python function. Return only the function body "
    "with its original indentation, without the signature or docstring, and "
    "without code fences.\n\n"
)


class HumanEval(Suite):
    id = "human_eval"
    profiles = ("default",)
    default_params: ClassVar[dict[str, Any]] = {
        "thinking": False,
        "temperature": 0.0,
        "multi_turn": False,
        "preserve_thinking": False,
    }
    runner = None  # injectable for tests

    def build(self, profile, ctx):
        problems = getattr(ctx, "human_eval", None) or data.human_eval_problems()
        return [
            Job(
                id=problem["task_id"],
                prompts=[Prompt(problem["entry_point"], INSTRUCTION + problem["prompt"])],
                params=dict(self.default_params),
                meta=problem,
            )
            for problem in problems
        ]

    def check(self, job, subjobs):
        return [Check(PASS) for _ in subjobs]  # verdicts come from the sandbox

    def finalize(self, jobs):
        programs: dict[str, str] = {}
        refs: list[tuple[str, SubJob]] = []
        for job, subjobs in jobs:
            for sub in subjobs:
                if sub.status in (ERROR, SKIPPED):
                    continue
                name = f"p{len(refs)}"
                programs[name] = humaneval.build_program(job.meta, sub.response)
                refs.append((name, sub))
        if not programs:
            return
        try:
            results = humaneval.evaluate(programs, runner=self.runner)
        except Exception as exc:  # noqa: BLE001 - sandbox failure is not a model failure
            for _, sub in refs:
                sub.status = ERROR
                sub.reason = f"sandbox error: {exc}"
            return
        for name, sub in refs:
            status = results.get(name, "error")
            sub.status = PASS if status == "pass" else FAIL
            sub.reason = None if status == "pass" else f"sandbox: {status}"
