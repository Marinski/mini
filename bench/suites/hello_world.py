"""hello_world: recall from a shared context; pipeline smoke test.

Prompts recovered verbatim from Protorikis's `rikis` agent log
(``agent-trials/llama-benchy/rikis-agent.log``, 6 Oct 2026): the job is one
multi-turn conversation — state your model, then two yes/no questions where
turn 3 must recall turn 2's answer.
"""

from __future__ import annotations

from typing import Any, ClassVar

from bench.suites import checks
from bench.suites.base import FAIL, PASS, Check, Job, Prompt, SubJob, Suite

PROMPTS = [
    Prompt(
        "State your model name and version. Do not explain, do not apologize, "
        "do not say you don't know. Just output the identifier string.",
        "State your model name and version. Do not explain, do not apologize, "
        "do not say you don't know. Just output the identifier string.",
    ),
    Prompt(
        "Is Today a calm day? Answer (in one word): yes/no",
        "Is Today a calm day? Answer (in one word): yes/no",
    ),
    Prompt(
        "Will it be calm Tomorrow too? Answer (in one word): yes/no",
        "Will it be calm Tomorrow too? Answer (in one word): yes/no",
    ),
]


class HelloWorld(Suite):
    id = "hello_world"
    profiles = ("default",)
    default_params: ClassVar[dict[str, Any]] = {
        "thinking": False,
        "temperature": 0.0,
        "multi_turn": True,
        "preserve_thinking": False,
    }

    def build(self, profile, ctx):
        return [Job(id="hello_world", prompts=list(PROMPTS), params=dict(self.default_params))]

    def check(self, job, subjobs):
        results = []
        for i, sub in enumerate(subjobs):
            if i == 0:
                results.append(self._model_name(sub))
            elif i == 1:
                results.append(self._question(sub))
            else:
                results.append(self._recall(sub, subjobs[1]))
        return results

    def _model_name(self, sub: SubJob) -> Check:
        if checks.is_identifier(sub.response):
            return Check(PASS)
        return Check(FAIL, f"not a model identifier: {checks.first_line(sub.response)!r}")

    def _question(self, sub: SubJob) -> Check:
        answer = checks.yes_no(sub.response)
        if answer is None:
            return Check(FAIL, f"not one-word yes/no: {checks.first_line(sub.response)!r}")
        return Check(PASS)

    def _recall(self, sub: SubJob, previous: SubJob) -> Check:
        expected = checks.yes_no(previous.response)
        answer = checks.yes_no(sub.response)
        if answer is None:
            return Check(FAIL, f"not one-word yes/no: {checks.first_line(sub.response)!r}")
        if expected is None:
            return Check(FAIL, "previous turn had no yes/no to recall")
        if answer != expected:
            return Check(FAIL, f"answer {answer!r} does not recall previous {expected!r}")
        return Check(PASS)
