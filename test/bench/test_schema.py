import json
from pathlib import Path

import pytest

from bench import schemas
from bench.schemas import SchemaError, validate_run

SCHEMA_PATH = Path(__file__).with_name("run.schema.json")


def minimal_run():
    return {
        "schema_version": 1,
        "run_id": "hello_world__default__m__20261006T000000Z",
        "suite": "hello_world",
        "profile": "default",
        "model": "m",
        "endpoint": "http://h:1/v1",
        "params": {"thinking": False},
        "started_at": "2026-10-06T00:00:00Z",
        "finished_at": "2026-10-06T00:00:01Z",
        "context_window": None,
        "context_source": "unknown",
        "jobs": [
            {
                "job_id": "j",
                "params": {"thinking": False},
                "sub_jobs": [
                    {
                        "label": "t",
                        "prompt_bytes": 1,
                        "prompt_tokens": 1,
                        "prompt_tokens_estimated": True,
                        "ttft_seconds": 0.1,
                        "generation_seconds": 0.2,
                        "stream_seconds": 0.3,
                        "output_tokens": 2,
                        "chunk_count": 2,
                        "cached_tokens": 0,
                        "tokens_per_second": 10.0,
                        "prefill_tokens_per_second": 5.0,
                        "response": "ok",
                        "reasoning": "",
                        "status": "pass",
                        "reason": None,
                    }
                ],
            }
        ],
        "summary": {
            "jobs": 1,
            "sub_jobs": 1,
            "passed": 1,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
            "pass_rate": 1.0,
            "median_ttft_seconds": 0.1,
            "median_tokens_per_second": 10.0,
            "median_cached_tokens": 0,
        },
    }


def test_valid_run_passes():
    validate_run(minimal_run())


def test_missing_top_level_field_fails():
    run = minimal_run()
    del run["summary"]
    with pytest.raises(SchemaError):
        validate_run(run)


def test_missing_subjob_field_fails():
    run = minimal_run()
    del run["jobs"][0]["sub_jobs"][0]["ttft_seconds"]
    with pytest.raises(SchemaError):
        validate_run(run)


def test_bad_status_fails():
    run = minimal_run()
    run["jobs"][0]["sub_jobs"][0]["status"] = "maybe"
    with pytest.raises(SchemaError):
        validate_run(run)


def test_wrong_type_fails():
    run = minimal_run()
    run["jobs"][0]["sub_jobs"][0]["chunk_count"] = "two"
    with pytest.raises(SchemaError):
        validate_run(run)


def test_schema_file_matches_validator():
    schema = json.loads(SCHEMA_PATH.read_text())
    assert set(schema["required"]) == set(schemas.RUN_REQUIRED)
    job = schema["properties"]["jobs"]["items"]
    assert set(job["required"]) == set(schemas.JOB_REQUIRED)
    sub = job["properties"]["sub_jobs"]["items"]
    assert set(sub["required"]) == set(schemas.SUBJOB_REQUIRED)
    assert set(sub["properties"]["status"]["enum"]) == schemas.VALID_STATUSES
    assert set(schema["properties"]["summary"]["required"]) == set(schemas.SUMMARY_REQUIRED)
