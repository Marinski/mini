"""multi_turn_2: KV-cache reuse in a growing conversation.

Three turns each append a large three.js chunk; the fourth appends one line and
asks for the identifier declared there, so the answer needs the whole cached
context. The fourth turn is where a 65,536-token server runs out of room
(step 4), and where a server without prefix caching is slow.
"""

from __future__ import annotations

from bench import code_context, data
from bench.code_context import require_lines
from bench.suites import checks
from bench.suites.base import FAIL, PASS, Check, Job, Prompt, SubJob, Suite

CACHE_TTFT_SECONDS = 5.0


def _chunk_prompt(part: int, chunk: str) -> str:
    return (
        f"Here is part {part} of the three.js source:\n\n{chunk}\n\n"
        "Reply with only the word OK."
    )


class MultiTurn2(Suite):
    id = "multi_turn_2"
    profiles = ("default",)

    def build(self, profile, ctx):
        lines = require_lines(ctx)
        chunks = code_context.windows(lines, 3)
        declaration = code_context.find_declaration(lines)
        if len(chunks) < 3 or declaration is None:
            raise data.DataMissing(data.DATA_DIR / data.THREE_JS_FILE)
        decl_line, decl_name = declaration
        prompts = [Prompt(f"part {i + 1}", _chunk_prompt(i + 1, c)) for i, c in enumerate(chunks)]
        prompts.append(
            Prompt(
                "one more line",
                "Here is one more line of the three.js source:\n\n"
                f"{decl_line}\n\nWhat is the name of the function or class declared "
                "on that line? Reply with only the identifier.",
            )
        )
        return [
            Job(
                id="multi_turn_2",
                prompts=prompts,
                params=dict(self.default_params),
                meta={"decl_name": decl_name},
            )
        ]

    def check(self, job, subjobs):
        results = []
        for i, sub in enumerate(subjobs):
            if i < 3:
                results.append(self._ack(sub))
            else:
                results.append(self._final(sub, job.meta["decl_name"]))
        return results

    def _ack(self, sub: SubJob) -> Check:
        word = checks.first_line(sub.response).strip(" .`*").lower()
        if word == "ok":
            return Check(PASS)
        return Check(FAIL, f"expected OK, got {checks.first_line(sub.response)!r}")

    def _final(self, sub: SubJob, name: str) -> Check:
        if name.lower() not in sub.response.lower():
            return Check(FAIL, f"expected {name!r}, got {checks.first_line(sub.response)!r}")
        if sub.ttft_seconds is not None and sub.ttft_seconds >= CACHE_TTFT_SECONDS:
            return Check(
                FAIL,
                f"correct but not cache-speed: TTFT {sub.ttft_seconds:.1f}s "
                f">= {CACHE_TTFT_SECONDS:.0f}s",
            )
        return Check(PASS)
