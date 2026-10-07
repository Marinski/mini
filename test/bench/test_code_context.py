
import pytest

from bench import code_context, data
from bench.suites.base import Job, SubJob
from bench.suites.context_caching_1 import ContextCaching1
from bench.suites.multi_turn_2 import MultiTurn2

THREE = data.DATA_DIR / data.THREE_JS_FILE
needs_three = pytest.mark.skipif(not THREE.exists(), reason="run bench/data/setup.py")


def _sub(response, ttft=0.5):
    return SubJob(label="x", prompt="", prompt_bytes=0, response=response, ttft_seconds=ttft)


def test_windows_are_byte_sized_and_non_overlapping():
    lines = [f"line {i:04d} " + "x" * 20 for i in range(200)]
    chunks = code_context.windows(lines, 3, bytes_each=400, gap=0)
    assert len(chunks) == 3
    assert chunks[0].splitlines()[0].startswith("line 0000")
    last_of_first = int(chunks[0].splitlines()[-1].split()[1])
    first_of_second = int(chunks[1].splitlines()[0].split()[1])
    assert first_of_second > last_of_first
    for chunk in chunks:
        assert len(chunk.encode()) < 500


def test_find_declaration():
    lines = ["// header", "export function foo() {", "class Bar {"]
    assert code_context.find_declaration(lines) == ("export function foo() {", "foo")
    assert code_context.find_declaration(lines, start=2) == ("class Bar {", "Bar")
    assert code_context.find_declaration(["// nothing"]) is None


@needs_three
def test_multi_turn_2_build():
    ctx = data.Context(three_js_lines=data.three_js_lines())
    jobs = MultiTurn2().build("default", ctx)
    assert len(jobs) == 1
    assert len(jobs[0].prompts) == 4
    assert jobs[0].meta["decl_name"]


@needs_three
def test_multi_turn_2_check():
    ctx = data.Context(three_js_lines=data.three_js_lines())
    suite = MultiTurn2()
    job = suite.build("default", ctx)[0]
    name = job.meta["decl_name"]

    good = [SubJob(label="p", prompt="", prompt_bytes=0, response="OK", ttft_seconds=0.5) for _ in range(3)]
    good.append(SubJob(label="p", prompt="", prompt_bytes=0, response=name, ttft_seconds=0.5))
    suite.apply_checks(job, good)
    assert [s.status for s in good] == ["pass", "pass", "pass", "pass"]

    bad = [SubJob(label="p", prompt="", prompt_bytes=0, response="OK", ttft_seconds=0.5) for _ in range(3)]
    bad.append(SubJob(label="p", prompt="", prompt_bytes=0, response="nope", ttft_seconds=0.5))
    suite.apply_checks(job, bad)
    assert bad[3].status == "fail"

    slow = [SubJob(label="p", prompt="", prompt_bytes=0, response="OK", ttft_seconds=0.5) for _ in range(3)]
    slow.append(SubJob(label="p", prompt="", prompt_bytes=0, response=name, ttft_seconds=9.0))
    suite.apply_checks(job, slow)
    assert slow[3].status == "fail"
    assert "cache-speed" in slow[3].reason


def test_context_caching_check():
    suite = ContextCaching1()
    job = Job(id="w", prompts=[], params={})
    subs = [
        _sub("OK", 30.0),  # cold, slow: not checked
        _sub("OK", 1.0),  # repeat, fast: pass
        _sub("OK", 30.0),  # cold
        _sub("OK", 9.0),  # repeat, slow: fail
    ]
    suite.apply_checks(job, subs)
    assert [s.status for s in subs] == ["pass", "pass", "pass", "fail"]
