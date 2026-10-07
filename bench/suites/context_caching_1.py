"""context_caching_1: KV reuse across cold and repeated context windows.

Eight windows of three.js source, each sent cold and then again (``-rep``). The
pass check is Protorikis's: every repeat's TTFT is under five seconds, which
only holds when the server serves the repeated prompt from its prefix cache.
"""

from __future__ import annotations

from typing import Any, ClassVar

from bench import code_context
from bench.code_context import require_lines
from bench.suites.base import FAIL, PASS, Check, Job, Prompt, SubJob, Suite

CACHE_TTFT_SECONDS = 5.0
WINDOWS = 8


def _prompt(chunk: str) -> str:
    return f"Here is a block of three.js source:\n\n{chunk}\n\nReply with only the word OK."


class ContextCaching1(Suite):
    id = "context_caching_1"
    profiles = ("default",)
    default_params: ClassVar[dict[str, Any]] = {"multi_turn": False}

    def build(self, profile, ctx):
        lines = require_lines(ctx)
        chunks = code_context.windows(lines, WINDOWS)
        jobs = []
        for i, chunk in enumerate(chunks):
            text = _prompt(chunk)
            jobs.append(
                Job(
                    id=f"window-{i + 1}",
                    prompts=[
                        Prompt(f"window-{i + 1}", text),
                        Prompt(f"window-{i + 1}-rep", text),
                    ],
                    params=dict(self.default_params),
                )
            )
        return jobs

    def check(self, job, subjobs):
        results = []
        for i, sub in enumerate(subjobs):
            if i % 2 == 0:
                results.append(Check(PASS))  # the cold request
            else:
                results.append(self._repeat(sub))
        return results

    def _repeat(self, sub: SubJob) -> Check:
        if sub.ttft_seconds is None:
            return Check(FAIL, "no TTFT for the repeat")
        if sub.cached_tokens is not None and sub.cached_tokens <= 0:
            return Check(FAIL, "repeat served no cached tokens (prefix caching off?)")
        if sub.ttft_seconds >= CACHE_TTFT_SECONDS:
            return Check(
                FAIL,
                f"repeat TTFT {sub.ttft_seconds:.1f}s >= {CACHE_TTFT_SECONDS:.0f}s "
                f"(cached_tokens={sub.cached_tokens})",
            )
        return Check(PASS)
