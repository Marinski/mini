"""multi_turn_1: two numbers given in turns 1-2, recalled and summed in 3-4.

Prompts recovered verbatim from Protorikis's agent log (6 Oct 2026).
"""

from __future__ import annotations

from bench.suites import checks
from bench.suites.base import Check, FAIL, PASS, Job, Prompt, SubJob, Suite

FIRST = 333
SECOND = 778
PROMPTS = [
    Prompt(f"The first number is {FIRST}", f"The first number is {FIRST}"),
    Prompt(f"The second number is {SECOND}", f"The second number is {SECOND}"),
    Prompt(
        "What is the first number? Print only the number without explanations "
        "or highlighting.",
        "What is the first number? Print only the number without explanations "
        "or highlighting.",
    ),
    Prompt(
        "What is the sum of both numbers? Print only the number without "
        "explanations or highlighting.",
        "What is the sum of both numbers? Print only the number without "
        "explanations or highlighting.",
    ),
]


class MultiTurn1(Suite):
    id = "multi_turn_1"
    profiles = ("default",)
    default_params = {
        "thinking": False,
        "temperature": 0.0,
        "multi_turn": True,
        "preserve_thinking": False,
    }

    def build(self, profile, ctx):
        return [Job(id="multi_turn_1", prompts=list(PROMPTS), params=dict(self.default_params))]

    def check(self, job, subjobs):
        results = []
        for i, sub in enumerate(subjobs):
            if i <= 1:
                results.append(Check(PASS))  # the informational turns
            elif i == 2:
                results.append(self._number(sub, FIRST, "first number"))
            else:
                results.append(self._number(sub, FIRST + SECOND, "sum"))
        return results

    def _number(self, sub: SubJob, expected: int, what: str) -> Check:
        if checks.numbers_equal(sub.response, expected):
            return Check(PASS)
        found = checks.ints(checks.strip_markdown(sub.response))
        return Check(FAIL, f"{what}: expected {expected}, got {found[:3]!r}")
