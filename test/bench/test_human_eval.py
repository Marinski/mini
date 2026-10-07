import shutil

import pytest

from bench import data, humaneval
from bench.suites.base import ERROR, SubJob
from bench.suites.human_eval import HumanEval

HUMANEVAL = data.DATA_DIR / "human_eval.jsonl"
needs_data = pytest.mark.skipif(not HUMANEVAL.exists(), reason="run bench/data/setup.py")


def _sub(response):
    return SubJob(label="x", prompt="", prompt_bytes=0, response=response)


def test_extract_body_strips_fences():
    assert humaneval.extract_body("def f():\n", "```python\n    return 1\n```") == "    return 1"


def test_extract_body_removes_echoed_prompt():
    prompt = 'def f(x):\n    """doc"""\n'
    response = prompt + "    return x\n"
    assert humaneval.extract_body(prompt, response) == "    return x"


@needs_data
def test_build_program_compiles_for_canonical_solutions():
    for problem in data.human_eval_problems():
        program = humaneval.build_program(problem, problem["canonical_solution"])
        compile(program, problem["task_id"], "exec")


@needs_data
def test_canonical_solutions_pass_and_empty_bodies_fail():
    problems = data.human_eval_problems()
    canonical = {
        f"c{i}": humaneval.build_program(p, p["canonical_solution"])
        for i, p in enumerate(problems)
    }
    empty = {
        f"e{i}": humaneval.build_program(p, "")
        for i, p in enumerate(problems)
    }
    good = humaneval.local_runner(canonical)
    bad = humaneval.local_runner(empty)
    passed = sum(1 for v in good.values() if v == "pass")
    assert passed == len(problems), f"{passed}/{len(problems)} canonical solutions passed"
    assert all(v != "pass" for v in bad.values()), "an empty body passed"


@needs_data
def test_finalize_applies_sandbox_verdicts():
    ctx = data.Context(human_eval=data.human_eval_problems()[:3])
    suite = HumanEval()
    suite.runner = lambda programs: {name: "pass" for name in programs}
    jobs = suite.build("default", ctx)
    pairs = []
    for job in jobs:
        subs = [_sub(job.meta["canonical_solution"])]
        suite.apply_checks(job, subs)
        pairs.append((job, subs))
    suite.finalize(pairs)
    assert all(s.status == "pass" for _, subs in pairs for s in subs)

    suite.runner = lambda programs: {name: "fail" for name in programs}
    for _, subs in pairs:
        for s in subs:
            s.status = "pass"
    suite.finalize(pairs)
    assert all(s.status == "fail" for _, subs in pairs for s in subs)


@needs_data
def test_finalize_leaves_errors_and_skips_alone():
    ctx = data.Context(human_eval=data.human_eval_problems()[:2])
    suite = HumanEval()
    called = {}
    suite.runner = lambda programs: called.update(programs) or {}
    jobs = suite.build("default", ctx)
    pairs = []
    for job in jobs:
        subs = [_sub("")]
        subs[0].status = ERROR
        pairs.append((job, subs))
    suite.finalize(pairs)
    assert called == {}  # nothing runnable
    assert pairs[0][1][0].status == ERROR


@pytest.mark.skipif(
    not shutil.which("docker") or not __import__("os").environ.get("BENCH_DOCKER_TESTS"),
    reason="set BENCH_DOCKER_TESTS=1 to build and exercise the sandbox",
)
@needs_data
def test_docker_sandbox_passes_canonical_solutions():
    problems = data.human_eval_problems()[:5]
    humaneval.build_image()
    programs = {
        f"p{i}": humaneval.build_program(p, p["canonical_solution"])
        for i, p in enumerate(problems)
    }
    assert all(v == "pass" for v in humaneval.docker_runner(programs).values())


# Answer shapes seen 7 Oct 2026 from llama-server, which strips the leading whitespace of a reply.
_FN = {
    "prompt": 'def f(xs):\n    """Doc."""\n',
    "test": "def check(c):\n    assert c([1, 2]) == [1, 2]\n    assert c([]) == []\n",
    "entry_point": "f",
}


def _runs(completion):
    ns = {}
    exec(humaneval.build_program(_FN, completion), ns)  # noqa: S102 - test-only, trusted input


def test_first_line_stripped_is_reindented():
    _runs("if not xs:\n        return []\n    out = []\n    for x in xs:\n        out.append(x)\n    return out")


def test_whole_body_one_level_too_shallow_is_reindented():
    _runs("out = []\nfor x in xs:\n    out.append(x)\nreturn out")


def test_first_line_opening_a_block_whose_child_is_shallowest():
    _runs("for x in [None]:\n    out = list(xs)\n    return out")


def test_first_line_opening_a_bracket_keeps_continuation_lines():
    _runs("table = {\n        'a': 1,\n    }\n    return list(xs)")


def test_full_function_answer_replaces_the_stub():
    _runs("def f(xs):\n    return list(xs)")
