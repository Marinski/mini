"""preserve_thinking_1: reasoning is kept across turns.

Thinking is on and reasoning is re-sent, wrapped in ``<think>``. Turn 1 asks for
two 20-digit numbers but prints only the first; turn 2 must return the second,
which can only come from turn 1's reasoning. Prompts recovered verbatim from
Protorikis's agent log (6 Oct 2026).
"""

from __future__ import annotations

from typing import Any, ClassVar

from bench.suites import checks
from bench.suites.base import FAIL, PASS, Check, Job, Prompt, SubJob, Suite

TURN1 = (
    "Generate two 20 digit numbers. Make sure to think of two numbers - I'll "
    "ask about the 2nd one later. But print only the first number - nothing "
    "else. Don't return Python code - return just the number."
)
TURN2 = (
    "Now print the second number you generated in the previous step. Do not "
    "generate new numbers - use the number you thought of in the first step. "
    "If you don't remember it, or didn't think of one, say 'I don't remember "
    "the number'."
)
PROMPTS = [Prompt(TURN1, TURN1), Prompt(TURN2, TURN2)]


class PreserveThinking1(Suite):
    id = "preserve_thinking_1"
    profiles = ("default",)
    default_params: ClassVar[dict[str, Any]] = {
        "thinking": True,
        "preserve_thinking": True,
        "temperature": 1.0,  # as Protorikis sends it (7 Oct 2026)
    }

    def build(self, profile, ctx):
        return [
            Job(
                id="preserve_thinking_1",
                prompts=list(PROMPTS),
                params=dict(self.default_params),
            )
        ]

    def check(self, job, subjobs):
        first, second = subjobs[0], subjobs[1]
        numbers = _unique(checks.find_digit_runs(first.reasoning, 20))
        if len(numbers) < 2:
            return [
                Check(FAIL, f"turn 1 reasoning had {len(numbers)} 20-digit numbers, need 2"),
                Check(FAIL, "turn 2 cannot be checked without two numbers in turn 1 reasoning"),
            ]
        # The first number is the one turn 1 printed, not the first one its reasoning names:
        # reasoning can mention an example ("like 20000000000000000000") before choosing (7 Oct 2026).
        printed = _unique(checks.find_digit_runs(first.response, 20))
        first_number = printed[0] if printed else numbers[0]
        others = [n for n in numbers if n != first_number]
        return [self._turn1(printed, numbers), self._turn2(second, others)]

    def _turn1(self, printed: list[str], numbers: list[str]) -> Check:
        if len(printed) > 1:
            return Check(FAIL, "turn 1 leaked the second number into its visible answer")
        if not printed or printed[0] not in numbers:
            return Check(FAIL, "turn 1 did not print the first number")
        return Check(PASS)

    def _turn2(self, sub: SubJob, others: list[str]) -> Check:
        if any(n in others for n in checks.find_digit_runs(sub.response, 20)):
            return Check(PASS)
        if "don't remember" in sub.response.lower() or "do not remember" in sub.response.lower():
            return Check(FAIL, "turn 2 did not recall the second number from reasoning")
        return Check(FAIL, "turn 2 did not contain the second number")


def _unique(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
