"""Core types shared by every suite, the runner and the reporter.

A *run* is one benchmark x profile x endpoint x model with its parameters.
A *job* is one conversation (one prompt, or the turns of a multi-turn job).
A *sub-job* is one request inside a job.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

# Sub-job status values.
OK = "ok"  # streamed successfully, not yet checked
PASS = "pass"
FAIL = "fail"
ERROR = "error"
SKIPPED = "skipped"

STATUSES = (OK, PASS, FAIL, ERROR, SKIPPED)


@dataclass
class Prompt:
    """One turn of a job: the label Protorikis shows, and the text we send."""

    label: str
    text: str


@dataclass
class Job:
    """One conversation."""

    id: str
    prompts: list[Prompt]
    params: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class SubJob:
    """One request: what we sent, what came back, how fast, how it scored."""

    label: str
    prompt: str
    prompt_bytes: int
    prompt_tokens: int | None = None
    prompt_tokens_estimated: bool = False
    ttft_seconds: float | None = None
    generation_seconds: float | None = None
    stream_seconds: float | None = None
    output_tokens: int | None = None
    chunk_count: int = 0
    cached_tokens: int | None = None
    response: str = ""
    reasoning: str = ""
    status: str = OK
    reason: str | None = None

    @property
    def tokens_per_second(self) -> float | None:
        if self.output_tokens is None or not self.generation_seconds:
            return None
        return self.output_tokens / self.generation_seconds

    @property
    def prefill_tokens_per_second(self) -> float | None:
        """Prompt tokens not served from cache over TTFT, when reported."""
        if (
            self.prompt_tokens is None
            or self.cached_tokens is None
            or not self.ttft_seconds
        ):
            return None
        prefill = self.prompt_tokens - self.cached_tokens
        if prefill < 0:
            return None
        return prefill / self.ttft_seconds

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "prompt_bytes": self.prompt_bytes,
            "prompt_tokens": self.prompt_tokens,
            "prompt_tokens_estimated": self.prompt_tokens_estimated,
            "ttft_seconds": self.ttft_seconds,
            "generation_seconds": self.generation_seconds,
            "stream_seconds": self.stream_seconds,
            "output_tokens": self.output_tokens,
            "chunk_count": self.chunk_count,
            "cached_tokens": self.cached_tokens,
            "tokens_per_second": self.tokens_per_second,
            "prefill_tokens_per_second": self.prefill_tokens_per_second,
            "response": self.response,
            "reasoning": self.reasoning,
            "status": self.status,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SubJob:
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class Check:
    """The outcome of checking one sub-job."""

    status: str
    reason: str | None = None


class Suite:
    """Base class: a benchmark knows how to build jobs and how to check them."""

    id: str = ""
    profiles: ClassVar[tuple[str, ...]] = ("default",)
    # Default per-suite parameters, merged over the CLI defaults.
    default_params: ClassVar[dict[str, Any]] = {
        "thinking": False,
        "temperature": 0.0,
        "multi_turn": True,
        "preserve_thinking": False,
    }

    def build(self, profile: str, ctx: Any) -> list[Job]:
        raise NotImplementedError

    def check(self, job: Job, subjobs: list[SubJob]) -> list[Check]:
        """Return one Check per sub-job, in order.

        Only sub-jobs whose status is ``ok`` need a verdict; errors and
        skips already carry theirs and are passed through.
        """
        raise NotImplementedError

    def apply_checks(self, job: Job, subjobs: list[SubJob]) -> None:
        checks = self.check(job, subjobs)
        if len(checks) != len(subjobs):
            raise ValueError(
                f"{self.id}: check() returned {len(checks)} verdicts for "
                f"{len(subjobs)} sub-jobs"
            )
        for sub, verdict in zip(subjobs, checks):
            if sub.status in (ERROR, SKIPPED):
                continue  # a failed request is not a failed answer
            sub.status = verdict.status
            sub.reason = verdict.reason

    def finalize(self, jobs: list[tuple[Job, list[SubJob]]]) -> None:
        """Optional post-pass over every job, e.g. batch code execution.

        Runs after all per-job checks; may overwrite pass/fail verdicts but
        never touches errors or skips.
        """
