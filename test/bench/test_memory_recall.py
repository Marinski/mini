
import pytest

from bench import code_context, data
from bench.suites.memory_recall_1 import MemoryRecall1, body_check

THREE = data.DATA_DIR / data.THREE_JS_FILE
needs_three = pytest.mark.skipif(not THREE.exists(), reason="run bench/data/setup.py")

EXPECTED = [f"    body line {i}" for i in range(1, 12)]


def test_body_check_passes_true_body():
    check = body_check("\n".join(EXPECTED), EXPECTED)
    assert check.status == "pass"


def test_body_check_passes_code_fence():
    check = body_check("```javascript\n" + "\n".join(EXPECTED) + "\n```", EXPECTED)
    assert check.status == "pass"


def test_body_check_fails_changed_line_in_first_eight():
    got = list(EXPECTED)
    got[2] = "    body line X"
    check = body_check("\n".join(got), EXPECTED)
    assert check.status == "fail"
    assert "first 8" in check.reason


def test_body_check_fails_missing_line():
    got = EXPECTED[:9] + EXPECTED[10:]  # drop a line after the first eight
    check = body_check("\n".join(got), EXPECTED)
    assert check.status == "fail"
    assert "missing" in check.reason


def test_body_check_fails_extra_line():
    got = EXPECTED + ["    a line that is not there"]
    check = body_check("\n".join(got), EXPECTED)
    assert check.status == "fail"
    assert "extra" in check.reason


def test_body_check_fails_101_lines():
    got = [f"line {i}" for i in range(101)]
    check = body_check("\n".join(got), got[:100])
    assert check.status == "fail"
    assert "100" in check.reason


def test_body_check_ignores_indentation():
    got = [line.strip() for line in EXPECTED]
    assert body_check("\n".join(got), EXPECTED).status == "pass"


def test_find_functions():
    lines = ["// header", "function a() {", "  return 1;", "}", "function b() {"]
    lines += ["  x;"] * 10 + ["}"]
    found = code_context.find_functions(lines, min_body=1, max_body=20)
    assert [f["name"] for f in found] == ["a", "b"]
    assert found[0]["body"] == ["  return 1;"]
    assert len(found[1]["body"]) == 10


@needs_three
def test_profiles_shapes_and_growth():
    ctx = data.Context(three_js_lines=data.three_js_lines())
    suite = MemoryRecall1()
    expected_jobs = {"eighths": 8, "quarters": 4, "halves": 2, "full": 1}
    largest = {}
    for profile, jobs_count in expected_jobs.items():
        jobs = suite.build(profile, ctx)
        assert len(jobs) == jobs_count, profile
        assert sum(len(j.prompts) for j in jobs) == 16, profile
        assert all(len(j.meta["expected"]) == len(j.prompts) for j in jobs)
        largest[profile] = max(len(p.text.encode()) for j in jobs for p in j.prompts)
    assert largest["eighths"] < largest["quarters"] < largest["halves"] < largest["full"]


@needs_three
def test_profile_check_passes_true_body():
    ctx = data.Context(three_js_lines=data.three_js_lines())
    suite = MemoryRecall1()
    job = suite.build("full", ctx)[0]
    subs = []
    for body in job.meta["expected"]:
        subs.append(_sub("\n".join(body)))
    suite.apply_checks(job, subs)
    assert all(s.status == "pass" for s in subs)


def _sub(response):
    from bench.suites.base import SubJob

    return SubJob(label="x", prompt="", prompt_bytes=0, response=response)
