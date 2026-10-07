"""Run one suite against one endpoint, one request at a time, under a lock.

* one stream per endpoint: a file lock per endpoint URL, so a second run waits;
* context window known before sending: a request that will not fit is recorded
  as ``skipped: exceeds context``, not as a model failure;
* multi-turn replay with optional ``preserve_thinking`` (reasoning re-sent
  inside ``<think>``), exactly as Protorikis's agent does.
"""

from __future__ import annotations

import fcntl
import tempfile
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from bench.client import DEFAULT_TEMPERATURE, Client, StreamResult
from bench.results import (
    SCHEMA_VERSION,
    append_index,
    make_run_id,
    summarize,
    utc_now,
    write_run,
)
from bench.suites.base import ERROR, OK, SKIPPED, Job, Prompt, SubJob, Suite

GLOBAL_DEFAULTS: dict[str, Any] = {
    "thinking": False,
    "temperature": DEFAULT_TEMPERATURE,
    "multi_turn": True,
    "preserve_thinking": False,
    "max_tokens": None,  # None -> per-mode default
}
MAX_TOKENS_THINKING_OFF = 1024
MAX_TOKENS_THINKING_ON = 8192
TEMPLATE_MARGIN = 16  # chat-template tokens the raw /tokenize count omits

_thread_locks: dict[str, threading.Lock] = {}
_thread_locks_guard = threading.Lock()


def _thread_lock(path: str) -> threading.Lock:
    with _thread_locks_guard:
        return _thread_locks.setdefault(path, threading.Lock())


def lock_path(endpoint: str, lock_dir: Path) -> Path:
    from bench.results import slug

    return Path(lock_dir) / f"{slug(endpoint)}.lock"


@contextmanager
def endpoint_lock(path: Path) -> Iterator[None]:
    """Block until this process (and this thread) owns the endpoint's lock."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _thread_lock(str(path)), path.open("w") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def effective_params(job_params: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    params = {**GLOBAL_DEFAULTS, **job_params, **overrides}
    if params.get("max_tokens") is None:
        params["max_tokens"] = (
            MAX_TOKENS_THINKING_ON if params.get("thinking") else MAX_TOKENS_THINKING_OFF
        )
    return params


def is_multi_turn(params: dict[str, Any]) -> bool:
    return bool(params.get("multi_turn") or params.get("preserve_thinking"))


def render_messages(messages: list[dict[str, Any]]) -> str:
    return "\n".join(f"{m['role']}: {m['content']}" for m in messages)


def _assistant_content(result: StreamResult, preserve_thinking: bool) -> str:
    response = result.response or ""
    if preserve_thinking and result.reasoning:
        return f"<think>\n{result.reasoning}\n</think>\n\n{response}"
    return response


def run(
    suite: Suite,
    profile: str,
    client: Client,
    *,
    overrides: dict[str, Any] | None = None,
    ctx: Any = None,
    results_dir: Path,
    ctx_override: int | None = None,
    lock: bool = True,
    lock_dir: Path | None = None,
    on_subjob: Callable[[SubJob], None] | None = None,
) -> dict[str, Any]:
    overrides = dict(overrides or {})
    started_at = utc_now()
    window = client.context_window(override=ctx_override)

    def _body() -> dict[str, Any]:
        jobs = suite.build(profile, ctx)
        run_jobs: list[dict[str, Any]] = []
        pairs: list[tuple[Job, list[SubJob]]] = []
        for job in jobs:
            params = effective_params(job.params, overrides)
            subjobs = _run_job(suite, job, client, params, window.tokens, on_subjob)
            suite.apply_checks(job, subjobs)
            pairs.append((job, subjobs))
            for sub in subjobs:
                if on_subjob:
                    on_subjob(sub)
            run_jobs.append(
                {
                    "job_id": job.id,
                    "params": params,
                    "sub_jobs": [s.to_dict() for s in subjobs],
                }
            )
        suite.finalize(pairs)
        # finalize may change verdicts after on_subjob already reported; re-sync
        for (job, subjobs), record in zip(pairs, run_jobs):
            record["sub_jobs"] = [s.to_dict() for s in subjobs]
        run_id = make_run_id(suite.id, profile, client.model, started_at)
        run_params = {**GLOBAL_DEFAULTS, **suite.default_params, **overrides}
        return {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "suite": suite.id,
            "profile": profile,
            "model": client.model,
            "endpoint": client.endpoint,
            "params": run_params,
            "started_at": started_at,
            "finished_at": utc_now(),
            "context_window": window.tokens,
            "context_source": window.source,
            "jobs": run_jobs,
            "summary": summarize(run_jobs),
        }

    if lock:
        directory = lock_dir or (Path(tempfile.gettempdir()) / "mini-bench-locks")
        with endpoint_lock(lock_path(client.endpoint, directory)):
            record = _body()
    else:
        record = _body()
    write_run(results_dir, record)
    append_index(results_dir, record)
    return record


def _run_job(
    suite: Suite,
    job: Job,
    client: Client,
    params: dict[str, Any],
    context_window: int | None,
    on_subjob: Callable[[SubJob], None] | None,
) -> list[SubJob]:
    multi_turn = is_multi_turn(params)
    history: list[dict[str, Any]] = []
    stopped_reason: str | None = None
    subjobs: list[SubJob] = []

    for prompt in job.prompts:
        sub = _blank_subjob(prompt)
        if stopped_reason is not None:
            sub.status = SKIPPED
            sub.reason = stopped_reason
            subjobs.append(sub)
            if on_subjob:
                on_subjob(sub)
            continue

        messages = (history if multi_turn else []) + [
            {"role": "user", "content": prompt.text}
        ]
        prompt_tokens, estimated = client.count_tokens(render_messages(messages))
        sub.prompt_tokens = prompt_tokens
        sub.prompt_tokens_estimated = estimated

        if context_window is not None and (
            prompt_tokens + params["max_tokens"] + TEMPLATE_MARGIN > context_window
        ):
            sub.status = SKIPPED
            sub.reason = (
                f"exceeds context: {prompt_tokens} prompt + "
                f"{params['max_tokens']} max_tokens > {context_window}"
            )
            if multi_turn:  # independent prompts in a job do not depend on each other
                stopped_reason = "previous turn exceeded context"
            subjobs.append(sub)
            if on_subjob:
                on_subjob(sub)
            continue

        result = client.stream_chat(
            messages,
            temperature=params.get("temperature"),
            max_tokens=params["max_tokens"],
            thinking=bool(params.get("thinking")),
            preserve_thinking=bool(params.get("preserve_thinking")),
        )
        _absorb(sub, result)
        if result.status == "error":
            if multi_turn:
                stopped_reason = "previous turn errored"
        elif multi_turn:
            history.append({"role": "user", "content": prompt.text})
            history.append(
                {
                    "role": "assistant",
                    "content": _assistant_content(result, bool(params.get("preserve_thinking"))),
                }
            )
        subjobs.append(sub)
        if on_subjob:
            on_subjob(sub)
    return subjobs


def _blank_subjob(prompt: Prompt) -> SubJob:
    return SubJob(
        label=prompt.label,
        prompt=prompt.text,
        prompt_bytes=len(prompt.text.encode("utf-8")),
    )


def _absorb(sub: SubJob, result: StreamResult) -> None:
    sub.ttft_seconds = result.ttft_seconds
    sub.generation_seconds = result.generation_seconds
    sub.stream_seconds = result.stream_seconds
    sub.output_tokens = result.output_tokens
    sub.chunk_count = result.chunk_count
    sub.cached_tokens = result.cached_tokens
    sub.response = result.response
    sub.reasoning = result.reasoning
    if result.status == "error":
        sub.status = ERROR
        sub.reason = result.error
    else:
        sub.status = OK
        if result.prompt_tokens is not None:
            sub.prompt_tokens = result.prompt_tokens
            sub.prompt_tokens_estimated = False
