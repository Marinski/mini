"""Validation for run records, plus a hand-kept JSON Schema mirror.

The JSON Schema in ``test/bench/run.schema.json`` is what the spec asks the
results file to validate against; ``validate_run`` is the same contract with no
third-party dependency (stdlib + httpx only).
"""

from __future__ import annotations

from typing import Any

from bench.results import SCHEMA_VERSION
from bench.suites.base import STATUSES

RUN_REQUIRED = {
    "schema_version": int,
    "run_id": str,
    "suite": str,
    "profile": str,
    "model": str,
    "endpoint": str,
    "params": dict,
    "started_at": str,
    "finished_at": str,
    "context_window": (int, type(None)),
    "context_source": str,
    "jobs": list,
    "summary": dict,
}

JOB_REQUIRED = {"job_id": str, "params": dict, "sub_jobs": list}

SUBJOB_REQUIRED = {
    "label": str,
    "prompt_bytes": int,
    "prompt_tokens": (int, type(None)),
    "prompt_tokens_estimated": bool,
    "ttft_seconds": (float, int, type(None)),
    "generation_seconds": (float, int, type(None)),
    "stream_seconds": (float, int, type(None)),
    "output_tokens": (int, type(None)),
    "chunk_count": int,
    "cached_tokens": (int, type(None)),
    "tokens_per_second": (float, int, type(None)),
    "prefill_tokens_per_second": (float, int, type(None)),
    "response": str,
    "reasoning": str,
    "status": str,
    "reason": (str, type(None)),
}

SUMMARY_REQUIRED = {
    "jobs": int,
    "sub_jobs": int,
    "passed": int,
    "failed": int,
    "errors": int,
    "skipped": int,
    "pass_rate": (float, type(None)),
    "median_ttft_seconds": (float, int, type(None)),
    "median_tokens_per_second": (float, int, type(None)),
    "median_cached_tokens": (float, int, type(None)),
}

VALID_STATUSES = set(STATUSES)


class SchemaError(ValueError):
    pass


def _check_fields(where: str, obj: Any, required: dict[str, Any]) -> None:
    if not isinstance(obj, dict):
        raise SchemaError(f"{where}: expected object, got {type(obj).__name__}")
    for key, expected in required.items():
        if key not in obj:
            raise SchemaError(f"{where}: missing field {key!r}")
        value = obj[key]
        if isinstance(expected, tuple):
            if not isinstance(value, expected):
                names = "/".join(t.__name__ for t in expected)
                raise SchemaError(f"{where}.{key}: expected {names}, got {type(value).__name__}")
        elif not isinstance(value, expected):
            raise SchemaError(
                f"{where}.{key}: expected {expected.__name__}, got {type(value).__name__}"
            )


def validate_run(run: Any) -> None:
    _check_fields("run", run, RUN_REQUIRED)
    if run["schema_version"] != SCHEMA_VERSION:
        raise SchemaError(f"run.schema_version: expected {SCHEMA_VERSION}")
    for i, job in enumerate(run["jobs"]):
        _check_fields(f"jobs[{i}]", job, JOB_REQUIRED)
        for j, sub in enumerate(job["sub_jobs"]):
            _check_fields(f"jobs[{i}].sub_jobs[{j}]", sub, SUBJOB_REQUIRED)
            if sub["status"] not in VALID_STATUSES:
                raise SchemaError(f"jobs[{i}].sub_jobs[{j}].status: {sub['status']!r}")
    _check_fields("summary", run["summary"], SUMMARY_REQUIRED)
