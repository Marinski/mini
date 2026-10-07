from bench.compare import compare_runs, render_compare
from bench.report import latest_per_model_suite, render


def record(run_id, model, suite, started_at, passed=3, failed=0, ttft=1.0, tps=20.0, window=65536):
    return {
        "run_id": run_id,
        "model": model,
        "suite": suite,
        "profile": "default",
        "started_at": started_at,
        "context_window": window,
        "jobs": [
            {
                "job_id": "j",
                "params": {},
                "sub_jobs": [
                    {"label": f"t{i}", "status": "pass" if i < passed else "fail"}
                    for i in range(passed + failed)
                ],
            }
        ],
        "summary": {
            "jobs": 1,
            "sub_jobs": passed + failed,
            "passed": passed,
            "failed": failed,
            "errors": 0,
            "skipped": 0,
            "pass_rate": passed / (passed + failed) if (passed + failed) else None,
            "median_ttft_seconds": ttft,
            "median_tokens_per_second": tps,
            "median_cached_tokens": None,
        },
    }


def test_latest_per_model_suite_wins():
    old = record("r1", "m", "hello_world", "2026-10-06T00:00:00Z", passed=1, failed=2)
    new = record("r2", "m", "hello_world", "2026-10-06T01:00:00Z", passed=3, failed=0)
    picked = latest_per_model_suite([old, new])
    assert len(picked) == 1
    assert picked[0]["run_id"] == "r2"


def test_render_table_numbers():
    text = render([record("r1", "qwen", "hello_world", "2026-10-06T00:00:00Z")])
    assert "### qwen" in text
    assert "hello_world" in text
    assert "100%" in text
    assert "3/3" in text
    assert "1.00" in text
    assert "20.00" in text
    assert "65536" in text


def test_render_empty():
    assert "No runs yet" in render([])


def test_compare_agreement():
    a = record("a", "m", "hello_world", "t0", passed=3, failed=0)
    b = record("b", "m", "hello_world", "t1", passed=2, failed=1)
    result = compare_runs(a, b)
    assert result["agreement"]["comparable"] == 3
    assert result["agreement"]["agree"] == 2
    assert result["agreement"]["rate"] == 2 / 3
    assert len(result["agreement"]["disagreements"]) == 1
    text = render_compare(result)
    assert "Agreement:" in text
    assert "2/3" in text


def test_compare_speed_within_ten_percent():
    a = record("a", "m", "s", "t0", ttft=1.0, tps=20.0)
    b = record("b", "m", "s", "t1", ttft=1.05, tps=21.0)
    result = compare_runs(a, b)
    assert result["speed"]["ttft_within_10pct"] is True
    assert result["speed"]["tokens_per_second_within_10pct"] is True
    far = record("c", "m", "s", "t2", ttft=2.0, tps=20.0)
    assert compare_runs(a, far)["speed"]["ttft_within_10pct"] is False


def test_compare_ignores_errors_and_skips():
    a = record("a", "m", "s", "t0", passed=1, failed=0)
    a["jobs"][0]["sub_jobs"].append({"label": "err", "status": "error"})
    b = record("b", "m", "s", "t1", passed=1, failed=0)
    b["jobs"][0]["sub_jobs"].append({"label": "err", "status": "skipped"})
    result = compare_runs(a, b)
    assert result["agreement"]["comparable"] == 1
    assert result["agreement"]["agree"] == 1
